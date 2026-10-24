import json
from pathlib import Path

import pytest

from bot.actions import Action, LegalActions
from bot.brains.tier2 import DEFAULTS, Tier2Brain, lock_margin
from bot.cards import parse_cards as P
from bot.opponent import OpponentModel, shrink
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, MatchInfo,
                          OppAction, Showdown)
from bot.state import GameState
from lab.engine import play_match
from lab.players import InProcessPlayer, PlayerSpec

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- opponent model

def test_shrink_formula() -> None:
    assert shrink(0, 0, 0.4, 10) == 0.4
    assert shrink(10, 10, 0.4, 10) == pytest.approx((10 + 4) / 20)
    assert shrink(900, 1000, 0.4, 10) == pytest.approx(0.8952, abs=1e-3)


def feed(model: OpponentModel, st: GameState, msgs, my_actions=None) -> None:
    my_actions = list(my_actions or [])
    for m in msgs:
        st.apply(m)
        if isinstance(m, ActRequest):
            st.record_my_action(my_actions.pop(0))
        model.update(st, m)


def hand_msgs(opp_actions_preflop, flop_opp=None, showdown=False):
    """We are SB: we act, then opp responds."""
    msgs = [HandStart(1, 0, 400, 400), HoleCards(P("Ah,Kd")),
            ActRequest(3, 1, 399, 398, LegalActions(fold=True, call=True))]
    msgs += [OppAction(a) for a in opp_actions_preflop]
    if flop_opp:
        msgs.append(BoardUpdate(1, P("2c,7d,9h")))
        msgs += [OppAction(a) for a in flop_opp]
    if showdown:
        msgs.append(Showdown(P("Qs,Qd")))
    msgs.append(HandEnd(0))
    return msgs


def test_model_counts() -> None:
    model, st = OpponentModel(k=0.0001), GameState()
    st.apply(MatchInfo())
    # Hand 1: we raise, opp folds.
    feed(model, st, hand_msgs([Action.fold()]), [Action.raise_to(6)])
    # Hand 2: we raise, opp calls, then raises on the flop; showdown.
    feed(model, st, hand_msgs([Action.call()], [Action.raise_to(10)], showdown=True),
         [Action.raise_to(6)])
    # Hand 3: we limp, opp raises.
    feed(model, st, hand_msgs([Action.raise_to(8)]), [Action.call()])
    assert model.raw("fold_to_raise") == (1, 2)
    assert model.raw("vpip") == (2, 3) and model.raw("pfr") == (1, 3)
    assert model.raw("aggression") == (1, 1)
    assert model.raw("wtsd") == (1, 1)
    assert model.get("vpip") == pytest.approx(2 / 3, abs=1e-3)


def test_adjustments_vs_station_and_bluffable() -> None:
    station = Tier2Brain()
    station.opp.stats["fold_to_raise"].count, station.opp.stats["fold_to_raise"].n = 0, 200
    station.opp.stats["vpip"].count, station.opp.stats["vpip"].n = 190, 200
    p = station.adjusted()
    assert p["bluff_freq"] < 0.1 * DEFAULTS["bluff_freq"]
    assert p["raise_equity"][1] < DEFAULTS["raise_equity"][1]
    assert p["value_frac"] > DEFAULTS["value_frac"]

    folder = Tier2Brain()
    folder.opp.stats["fold_to_raise"].count, folder.opp.stats["fold_to_raise"].n = 180, 200
    assert folder.adjusted()["bluff_freq"] > DEFAULTS["bluff_freq"]


def test_shipped_config_matches_known_keys() -> None:
    data = json.loads((ROOT / "bot" / "config" / "tier2.json").read_text())
    assert {k for k in data if not k.startswith("_")} <= set(DEFAULTS)


# --------------------------------------------------------------------------- endgame lock

def lock_state(hands: int, played: int, bankroll: int, seat: int, committed: int) -> GameState:
    st = GameState()
    st.apply(MatchInfo(hands=hands, sb=1, bb=2))
    st.hands_played, st.bankroll = played, bankroll
    st.apply(HandStart(played, seat, 400, 400))
    st.apply(ActRequest(3, 1, 400 - committed, 398, LegalActions(fold=True, call=True)))
    return st


def test_lock_margin_math() -> None:
    # 10 hands, 5 played, current = hand 5, we're SB (seat 0) having posted 1.
    # Future hands 6..9 -> seats 1,0,1,0 -> costs 2+1+2+1 = 6. Margin = lead - 1 - 6.
    assert lock_margin(lock_state(10, 5, 8, 0, 1)) == 1
    assert lock_margin(lock_state(10, 5, 7, 0, 1)) == 0       # exactly a draw: not locked
    # As BB (seat 1) having posted 2: future seats 0,1,0,1 -> 6 as well.
    assert lock_margin(lock_state(10, 5, 9, 1, 2)) == 1
    # Odd number of future hands depends on our seat.
    assert lock_margin(lock_state(10, 6, 0, 0, 1)) == -1 - (2 + 1 + 2)
    assert lock_margin(lock_state(10, 6, 0, 1, 2)) == -2 - (1 + 2 + 1)
    # Conservative mode: every future hand costs a big blind.
    assert lock_margin(lock_state(10, 5, 8, 0, 1), assume_alternating=False) == 8 - 1 - 8


def test_lock_forces_check_fold() -> None:
    brain = Tier2Brain({"bluff_freq": 0.0})
    st = lock_state(10, 9, 50, 0, 1)            # last hand, +50 up
    st.apply(HoleCards(P("Ah,Ad")))
    legal = LegalActions(fold=True, call=True, raise_min=4, raise_max=400)
    assert brain.decide(st, legal, 0.02) == Action.fold()
    assert brain.locked_decisions == 1


@pytest.mark.parametrize("opp", ["all_in", "maniac", "random_legal"])
@pytest.mark.parametrize("first_seat_player", [0, 1])
def test_lock_guarantees_win_in_real_match(opp: str, first_seat_player: int) -> None:
    # Pretend we're already up by exactly enough to lock from the first decision of a
    # 30-hand match (15 SB + 15 BB = 45, plus the blind in hand 0): we must finish ahead
    # whatever the opponent does and whichever seat we start in.
    lead = 45 + 2 + 1
    me = InProcessPlayer(Tier2Brain())
    me.bot.state.bankroll = lead
    players = [me, PlayerSpec.brain(opp).build()]
    if first_seat_player == 1:
        players.reverse()
    m = play_match(players, seed=3, hands=30)
    my_index = players.index(me)
    assert lead + m.chips[my_index] > 0
    assert me.bot.brain.locked_decisions > 0


def test_tier2_plays_legally() -> None:
    m = play_match([PlayerSpec.brain("tier2").build(), PlayerSpec.brain("maniac").build()],
                   seed=4, hands=120)
    assert m.errors == [0, 0] and m.forfeit is None
