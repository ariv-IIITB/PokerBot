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
    station.opponent.stats.stats["fold_to_raise"].count, station.opponent.stats.stats["fold_to_raise"].n = 0, 200
    station.opponent.stats.stats["vpip"].count, station.opponent.stats.stats["vpip"].n = 190, 200
    p = station.adjusted()
    assert p["bluff_freq"] < 0.1 * DEFAULTS["bluff_freq"]
    assert p["raise_equity"][1] < DEFAULTS["raise_equity"][1]
    assert p["value_frac"] > DEFAULTS["value_frac"]

    folder = Tier2Brain()
    folder.opponent.stats.stats["fold_to_raise"].count, folder.opponent.stats.stats["fold_to_raise"].n = 180, 200
    assert folder.adjusted()["bluff_freq"] > DEFAULTS["bluff_freq"]


def _with_aggression(rate: float) -> Tier2Brain:
    b = Tier2Brain()
    b.opponent.stats.stats["aggression_all"].count, b.opponent.stats.stats["aggression_all"].n = int(rate * 400), 400
    return b


def test_bet_pressure_relaxes_only_vs_extreme_aggression() -> None:
    base = DEFAULTS["bet_pressure"]
    assert Tier2Brain().adjusted()["bet_pressure"] == base           # unknown opponent
    assert _with_aggression(0.45).adjusted()["bet_pressure"] == base  # normal bots (~0.4-0.45)
    maniac = _with_aggression(0.85).adjusted()["bet_pressure"]
    shover = _with_aggression(1.0).adjusted()["bet_pressure"]
    assert 0 < shover < maniac < base and shover < 0.1 * base
    off = Tier2Brain({"pressure_aggr_shift": 0.0})
    off.opponent.stats.stats["aggression_all"].count = off.opponent.stats.stats["aggression_all"].n = 400
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


# --------------------------------------------------------------------------- phase E: bluff-catching and sizing

from bot.actions import RAISE  # noqa: E402
from bot.protocol import BoardUpdate  # noqa: E402


def test_the_river_call_rule_starts_value_heavy_and_follows_the_bluff_index() -> None:
    brain = Tier2Brain({"river_bluff_slope": 0.5})
    assert brain.adjusted(1)["call_margin"] == pytest.approx(brain.adjusted(0)["call_margin"])   # before the turn: no rule
    v_heavy = brain.adjusted(3)["call_margin"]
    assert v_heavy == pytest.approx(brain.adjusted(1)["call_margin"] + 0.5 * (0.22 - 0.15))
    for _ in range(300):                                                  # they bluff a lot at showdown
        brain.opponent.spots.spots["bluff_index"].add(True)
    over_bluffer = brain.adjusted(3)["call_margin"]
    assert over_bluffer < brain.adjusted(1)["call_margin"] < v_heavy      # calls wider than the old rule
    brain2 = Tier2Brain({"river_bluff_slope": 0.5})
    for _ in range(300):                                                  # never a bluff
        brain2.opponent.spots.spots["bluff_index"].add(False)
    assert brain2.adjusted(2)["call_margin"] > v_heavy                    # the cap keeps it bounded
    assert brain2.adjusted(2)["call_margin"] - brain.p["call_margin"] <= 0.5 * 0.22 + 1e-9


def test_the_rule_is_off_at_zero_slope() -> None:
    brain = Tier2Brain({"river_bluff_slope": 0.0})
    assert brain.adjusted(3)["call_margin"] == pytest.approx(brain.adjusted(1)["call_margin"])


def raise_state(pot: int, my_stack: int, my_bet: int = 0, tocall: int = 0, street: int = 3):
    st = GameState()
    st.apply(MatchInfo(hands=400, sb=1, bb=2, stack=200))
    st.apply(HandStart(0, 1, 200, 200))
    st.apply(HoleCards(P("As,Kd")))
    st.apply(BoardUpdate(street, P("2c,7d,9h,Jd,Qs")[:{1: 3, 2: 4, 3: 5}[street]]))
    st.apply(ActRequest(pot, tocall, my_stack, 200 - 20, LegalActions(
        fold=tocall > 0, check=tocall == 0, call=tocall > 0, raise_min=my_bet + tocall + 2,
        raise_max=my_bet + my_stack), None, my_bet, my_bet + tocall))
    return st


def test_a_raise_that_leaves_crumbs_goes_all_in() -> None:
    st = raise_state(pot=40, my_stack=60)
    h = st.hand
    legal = LegalActions(check=True, raise_min=2, raise_max=60)
    crumbs = Tier2Brain.no_leftovers(Action.raise_to(50), h, legal, 0.25)    # 10 behind < 25% of 90
    assert crumbs == Action.raise_to(60)
    kept = Tier2Brain.no_leftovers(Action.raise_to(30), h, legal, 0.25)      # 30 behind >= 25% of 70
    assert kept == Action.raise_to(30)
    assert Tier2Brain.no_leftovers(Action.raise_to(60), h, legal, 0.25) == Action.raise_to(60)  # already all-in


def test_the_leftover_rule_is_off_by_default_and_only_for_value_raises() -> None:
    st = raise_state(pot=40, my_stack=60)
    legal = LegalActions(check=True, raise_min=2, raise_max=60)
    off = Tier2Brain()
    assert off.p["leftover_frac"] == 0.0
    on = Tier2Brain({"leftover_frac": 0.25})
    big = on.sized_raise(1.1, "value", 0.9, st, legal, on.adjusted(3))      # 1.1 x 40 = 44: leaves 16 < 25% of 84
    assert big == Action.raise_to(60)
    bluff = on.sized_raise(1.1, "bluff", 0.1, st, legal, on.adjusted(3))
    assert bluff == Action.raise_to(44)                                      # bluffs are not rounded up


def test_ev_sizing_picks_a_legal_candidate_and_follows_the_fold_rates() -> None:
    st = raise_state(pot=40, my_stack=150)
    legal = LegalActions(check=True, raise_min=2, raise_max=150)
    brain = Tier2Brain({"ev_sizing": True})
    p = brain.adjusted(3)
    for eq in (0.9, 0.1):
        a = brain.sized_raise(0.66, "value" if eq > 0.5 else "bluff", eq, st, legal, p)
        assert a.kind == RAISE and legal.raise_min <= a.amount <= legal.raise_max
    # a strong hand against an opponent who never folds wants a size it gets paid at;
    # a pure bluff against one who folds a lot to everything wants the cheapest size
    for b in ("fold_small", "fold_mid", "fold_big"):
        brain.opponent.spots.spots[b].hits, brain.opponent.spots.spots[b].n = 0, 400            # never folds
    value = brain.sized_raise(0.66, "value", 0.95, st, legal, brain.adjusted(3))
    for b in ("fold_small", "fold_mid", "fold_big"):
        brain.opponent.spots.spots[b].hits, brain.opponent.spots.spots[b].n = 400, 400          # always folds
    bluff = brain.sized_raise(0.66, "bluff", 0.1, st, legal, brain.adjusted(3))
    assert value.amount > bluff.amount
    assert bluff.amount <= 40 * 0.66 + 2                                       # the small candidate


def test_a_raise_is_noted_for_the_fold_statistics() -> None:
    brain = Tier2Brain({"lock_enabled": False, "bluff_freq": 0.0})
    st = raise_state(pot=40, my_stack=150)
    st.apply(ActRequest(40, 0, 150, 150, LegalActions(check=True, raise_min=2, raise_max=150), None, 0, 0))
    a = brain.decide(st, LegalActions(check=True, raise_min=2, raise_max=150), 0.02)
    if a.kind == RAISE:
        assert brain.opponent.spots._pending is not None


# --------------------------------------------------------------------------- phase E2: embedded tables

def test_the_embedded_tables_load_and_rank_hands() -> None:
    brain = Tier2Brain()
    assert brain.perception.tables is not None and brain.perception.tables.meta["variant"] == "discard_holdem"
    assert brain.perception.tables.classes.size == 3 and len(brain.perception.tables.eq_random) == 1755
    assert brain.perception.tables.eq_range is not None
    share = brain.perception.tables.start_share
    assert share(P("As,Ah,Kd")) > share(P("9c,9d,2h")) > share(P("Ks,Qs,Js")) > share(P("Ts,9s,8s")) > share(P("7c,2d,3h"))
    assert 0.25 < share(P("7c,2d,3h")) < 0.45 and 0.75 < share(P("As,Ah,Ad")) < 0.9


def test_preflop_equity_comes_from_the_table_without_sampling() -> None:
    import time
    brain = Tier2Brain({"lock_enabled": False})
    st = GameState()
    st.apply(MatchInfo(hands=400, sb=1, bb=2, stack=200))
    st.apply(HandStart(0, 0, 200, 200))
    st.apply(HoleCards(P("As,Ah,Kd")))
    st.apply(ActRequest(3, 1, 199, 198, LegalActions(fold=True, call=True, raise_min=4, raise_max=200), None, 1, 2))
    t0 = time.perf_counter()
    eq = brain.situation(st).equity(0.5)
    assert time.perf_counter() - t0 < 0.01                       # a lookup, not a simulation
    assert eq == brain.perception.tables.start_share(P("As,Ah,Kd"))
