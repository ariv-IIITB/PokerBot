import json
from pathlib import Path

import pytest

from bot.actions import Action, LegalActions
from bot.brains.tier2 import DEFAULTS, Tier2Brain, lock_margin
from bot.cards import parse_cards as P
from bot.game.rules_spec import to_rules
from bot.opponent import OpponentModel, shrink
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, MatchInfo,
                          OppAction, Showdown)
from bot.state import GameState
from lab.engine import play_match
from lab.players import InProcessPlayer, PlayerSpec
from variant.spec import load_catalog

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
    # every street: hand 2 call (pre) + raise (flop), hand 3 raise (pre)
    assert model.raw("aggression_all") == (2, 3)


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


def _with_aggression(rate: float) -> Tier2Brain:
    b = Tier2Brain()
    b.opp.stats["aggression_all"].count, b.opp.stats["aggression_all"].n = int(rate * 400), 400
    return b


def test_bet_pressure_relaxes_only_vs_extreme_aggression() -> None:
    base = DEFAULTS["bet_pressure"]
    assert Tier2Brain().adjusted()["bet_pressure"] == base           # unknown opponent
    assert _with_aggression(0.45).adjusted()["bet_pressure"] == base  # normal bots (~0.4-0.45)
    maniac = _with_aggression(0.85).adjusted()["bet_pressure"]
    shover = _with_aggression(1.0).adjusted()["bet_pressure"]
    assert 0 < shover < maniac < base and shover < 0.1 * base
    off = Tier2Brain({"pressure_aggr_shift": 0.0})
    off.opp.stats["aggression_all"].count = off.opp.stats["aggression_all"].n = 400
    assert off.adjusted()["bet_pressure"] == base                     # switch works


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


# --------------------------------------------------------------------------- lock on discard_holdem

DH_RULES = to_rules(load_catalog()["discard_holdem"])


def worst_case_cost(hands: int, first_seat: int) -> int:
    """What check/folding every hand after the first costs: 1 as the button (SB), 2 as the BB."""
    return sum(1 if (first_seat + j) % 2 == 0 else 2 for j in range(1, hands))


@pytest.mark.parametrize("hands", [400, 1000])
@pytest.mark.parametrize("seat", [0, 1])
def test_lock_margin_on_discard_holdem_at_both_match_lengths(hands: int, seat: int) -> None:
    committed = 1 if seat == 0 else 2
    need = worst_case_cost(hands, seat) + committed        # a lead of exactly this is not a lock
    st = lock_state(hands, 0, need, seat, committed)
    assert lock_margin(st, rules=DH_RULES) == 0
    assert lock_margin(lock_state(hands, 0, need + 1, seat, committed), rules=DH_RULES) == 1
    assert lock_margin(lock_state(hands, 0, need - 1, seat, committed), rules=DH_RULES) == -1
    # 400 hands: 199 + 200 * 2 = 599 more than the blind in hand 0 (button first)
    if (hands, seat) == (400, 0):
        assert need == 600


@pytest.mark.parametrize("hands", [400, 1000])
@pytest.mark.parametrize("lead", [-300, -1, 0])
def test_it_never_locks_without_a_lead(hands: int, lead: int) -> None:
    """Locked means check/fold forever, so a zero or negative lead must never get there, at
    any point of the match (first hand, middle, last hand)."""
    for played in (0, hands // 2, hands - 1):
        for seat in (0, 1):
            st = lock_state(hands, played, lead, seat, 1 if seat == 0 else 2)
            assert lock_margin(st, rules=DH_RULES) < 0
            brain = Tier2Brain({"bluff_freq": 0.0})
            st.apply(HoleCards(P("Ah,Ad,Ac")))
            brain.decide(st, LegalActions(fold=True, call=True, raise_min=4, raise_max=200), 0.005)
            assert brain.locked_decisions == 0


def test_the_lock_lifts_as_soon_as_the_lead_is_gone() -> None:
    """The lock is re-evaluated at every decision: it holds only while the lead covers the worst
    case, and a shrinking lead hands the decision back to the normal strategy."""
    brain = Tier2Brain({"bluff_freq": 0.0})
    legal = LegalActions(fold=True, call=True, raise_min=4, raise_max=200)
    for bankroll, locked in ((60, True), (4, True), (3, False), (-20, False)):
        st = lock_state(10, 8, bankroll, 0, 1)            # hand 8 of 10: one future hand, as BB (2)
        st.apply(HoleCards(P("Ah,Ad,Ac")))
        before = brain.locked_decisions
        brain.decide(st, legal, 0.005)
        assert (brain.locked_decisions == before + 1) == locked, bankroll


@pytest.mark.parametrize("hands", [400, 1000])
@pytest.mark.parametrize("opp", ["all_in", "maniac"])
@pytest.mark.parametrize("first", [0, 1])
def test_a_locked_match_cannot_be_lost_on_discard_holdem(hands: int, opp: str, first: int) -> None:
    """Start with exactly the smallest locking lead and let the opponent do its worst: we finish
    ahead (match won) in both seat orders, because every decision is check/fold."""
    seat = first            # player 0 is the button in hand 0
    lead = worst_case_cost(hands, seat) + (1 if seat == 0 else 2) + 1
    me = InProcessPlayer(Tier2Brain(game=DH_RULES))
    me.bot.state.bankroll = lead
    players = [me, PlayerSpec.brain(opp).build()]
    if first == 1:
        players.reverse()
    m = play_match(players, load_catalog()["discard_holdem"], seed=11, hands=hands)
    assert m.errors == [0, 0] and m.forfeit is None
    assert lead + m.chips[players.index(me)] > 0
    assert me.bot.brain.locked_decisions > 0
