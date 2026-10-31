"""Phase E3: the opponent-stats module. The prior dominates early, the gate holds below 20
samples, the cap holds, and the feeding follows what the opponent does."""
import numpy as np
import pytest

from bot.actions import Action
from bot.cards import FULL_DECK, parse_cards as P
from bot.game.rules_spec import to_rules
from bot.protocol import HandEnd, HandStart, HoleCards, MatchInfo, OppAction, Showdown, BoardUpdate
from bot.state import GameState
from bot.strategy.oppstats import (CAP, GATE, POPULATION, OppStats, Spot, hand_percentile,
                                   size_bucket)
from variant.spec import load_catalog

EV = to_rules(load_catalog()["discard_holdem"]).evaluator


def test_the_prior_dominates_early() -> None:
    s = Spot(0.15)
    for _ in range(3):
        s.add(True)                                  # three bluffs in a row
    assert s.mean() == pytest.approx((3 + 0.15 * 15) / 18)
    assert 0.15 < s.mean() < 0.35                    # moved, but nowhere near 1.0


def test_the_gate_holds_below_twenty_samples() -> None:
    s = Spot(0.15)
    for _ in range(GATE - 1):
        s.add(True)
    assert s.mean() > 0.5 and s.shift() == 0.0       # a big raw move, but play does not change
    s.add(True)
    assert s.shift() > 0.0                           # the 20th observation opens the gate


def test_the_cap_holds_both_ways() -> None:
    hi, lo = Spot(0.30), Spot(0.30)
    for _ in range(500):
        hi.add(True)
        lo.add(False)
    assert hi.shift() == pytest.approx(CAP) and lo.shift() == pytest.approx(-CAP)
    assert hi.shift(cap=0.05) == pytest.approx(0.05)


def test_fold_prob_starts_at_the_population_prior_and_moves_within_the_cap() -> None:
    st = OppStats()
    assert st.fold_prob(0.33, 1) == pytest.approx(POPULATION["fold_small"])
    assert st.fold_prob(1.2, 3) == pytest.approx(POPULATION["fold_big"])
    for _ in range(200):
        st.spots["fold_big"].add(True)
        st.spots["fold_river"].add(True)
    assert st.fold_prob(1.2, 3) <= POPULATION["fold_big"] + CAP + 1e-9


def test_size_buckets() -> None:
    assert [size_bucket(f) for f in (0.2, 0.49, 0.5, 0.89, 0.9, 2.0)] == \
        ["fold_small", "fold_small", "fold_mid", "fold_mid", "fold_big", "fold_big"]


def hand_with_history(actions) -> GameState:
    st = GameState()
    st.apply(MatchInfo(hands=400, sb=1, bb=2, stack=200))
    st.apply(HandStart(0, 0, 200, 200))
    st.apply(HoleCards(P("As,Kd")))
    return st


def test_folds_to_our_raises_are_counted_by_size_and_street() -> None:
    stats, st = OppStats(), hand_with_history([])
    st.apply(BoardUpdate(1, P("2c,7d,9h")))
    stats.note_raise(1, 0.66)
    msg = OppAction(Action.fold())
    st.apply(msg)
    stats.update(st, msg)
    assert (stats.spots["fold_mid"].n, stats.spots["fold_mid"].hits) == (1, 1)
    assert (stats.spots["fold_flop"].n, stats.spots["fold_flop"].hits) == (1, 1)
    stats.note_raise(2, 1.5)                          # a call answers an overbet on the turn
    msg = OppAction(Action.call())
    st.apply(msg)
    stats.update(st, msg)
    assert (stats.spots["fold_big"].n, stats.spots["fold_big"].hits) == (1, 0)
    stats.update(st, OppAction(Action.check()))       # no raise pending: nothing counted
    assert stats.spots["fold_big"].n == 1 and stats.spots["fold_small"].n == 0


def test_a_hand_end_clears_a_pending_raise() -> None:
    stats, st = OppStats(), hand_with_history([])
    stats.note_raise(1, 0.5)
    stats.update(st, HandEnd(3))
    stats.update(st, OppAction(Action.fold()))
    assert stats.spots["fold_mid"].n == 0


def test_bluff_index_from_showdowns() -> None:
    stats, st = OppStats(), hand_with_history([])
    st.apply(BoardUpdate(1, P("2c,7d,9h")))
    st.apply(BoardUpdate(2, P("2c,7d,9h,Jd")))
    st.apply(BoardUpdate(3, P("2c,7d,9h,Jd,Qs")))
    pct = lambda opp, board: hand_percentile(EV, opp, board, FULL_DECK)     # noqa: E731
    st.apply(OppAction(Action.raise_to(20)))          # they bet the river
    st.hand.history[-1] = st.hand.history[-1].__class__(3, "opp", Action.raise_to(20))
    # a bluff: 3-high showing down
    msg = Showdown(P("3d,4c"))
    st.apply(msg)
    stats.update(st, msg, pct)
    # a value bet: a set
    msg = Showdown(P("9c,9d"))
    stats.update(st, msg, pct)
    s = stats.spots["bluff_index"]
    assert (s.n, s.hits) == (2, 1)


def test_hand_percentile_orders_hands() -> None:
    board = P("2c,7d,9h,Jd,Qs")
    nuts_ish = hand_percentile(EV, P("9c,9d"), board, FULL_DECK)       # a set of nines
    middle = hand_percentile(EV, P("Ac,Kd"), board, FULL_DECK)         # ace high
    junk = hand_percentile(EV, P("3d,4c"), board, FULL_DECK)           # four high
    assert nuts_ish > 0.9 and junk < 0.2 and junk < middle < nuts_ish


# --------------------------------------------------------------------------- Phase G spots

from bot.actions import Action as A  # noqa: E402
from bot.state import ActionRecord, ME, OPP  # noqa: E402
from bot.strategy.oppstats import spot_events  # noqa: E402


def rec(street, actor, action):
    return ActionRecord(street, actor, action)


def events(*recs):
    return dict(spot_events(list(recs)))


def test_answers_to_our_open_and_3bet() -> None:
    assert events(rec(0, ME, A.raise_to(5)), rec(0, OPP, A.fold())) == {"fold_to_open": True, "three_bet": False}
    assert events(rec(0, ME, A.raise_to(5)), rec(0, OPP, A.raise_to(18))) == \
        {"fold_to_open": False, "three_bet": True}
    assert events(rec(0, ME, A.raise_to(5)), rec(0, OPP, A.call())) == {"fold_to_open": False, "three_bet": False}
    # we re-raise their raise (we are the big blind): they fold / call
    assert events(rec(0, OPP, A.raise_to(5)), rec(0, ME, A.raise_to(18)), rec(0, OPP, A.fold())) == \
        {"fold_to_3bet": True}
    assert events(rec(0, OPP, A.raise_to(5)), rec(0, ME, A.raise_to(18)), rec(0, OPP, A.call())) == \
        {"fold_to_3bet": False}


def test_raise_vs_limp() -> None:
    assert events(rec(0, ME, A.call()), rec(0, OPP, A.raise_to(8))) == {"raise_vs_limp": True}
    assert events(rec(0, ME, A.call()), rec(0, OPP, A.check())) == {"raise_vs_limp": False}
    assert events(rec(0, OPP, A.call())) == {}                      # their own limp is not this spot


def test_flop_spots_follow_the_preflop_aggressor() -> None:
    pre_us = [rec(0, ME, A.raise_to(5)), rec(0, OPP, A.call())]
    pre_them = [rec(0, OPP, A.raise_to(5)), rec(0, ME, A.call())]
    # we raised preflop, bet the flop: they fold (a miss of cbet: it is not their spot)
    assert events(*pre_us, rec(1, OPP, A.check()), rec(1, ME, A.raise_to(4)), rec(1, OPP, A.fold())) == \
        {"fold_to_cbet": True, "check_raise": False}
    assert events(*pre_us, rec(1, OPP, A.check()), rec(1, ME, A.raise_to(4)), rec(1, OPP, A.raise_to(12))) == \
        {"fold_to_cbet": False, "check_raise": True}
    # they raised preflop: do they c-bet when no bet faces them?
    assert events(*pre_them, rec(1, OPP, A.raise_to(4))) == {"cbet": True}
    assert events(*pre_them, rec(1, OPP, A.check())) == {"cbet": False}
    assert events(*pre_us, rec(1, ME, A.check()), rec(1, OPP, A.check())) == {}      # no aggressor: not a c-bet


def test_turn_and_river_bets_when_unfaced() -> None:
    pre = [rec(0, ME, A.raise_to(5)), rec(0, OPP, A.call())]
    flop = [rec(1, OPP, A.check()), rec(1, ME, A.check())]
    assert events(*pre, *flop, rec(2, OPP, A.raise_to(8))) == {"turn_bet": True}
    assert events(*pre, *flop, rec(2, OPP, A.check())) == {"turn_bet": False}
    assert events(*pre, *flop, rec(2, OPP, A.check()), rec(2, ME, A.check()),
                  rec(3, OPP, A.raise_to(12))) == {"river_bet": True}
    # facing our bet is the fold-to-bet spots' business, not turn_bet
    assert "turn_bet" not in events(*pre, *flop, rec(2, OPP, A.check()), rec(2, ME, A.raise_to(8)),
                                    rec(2, OPP, A.call()))


def test_stats_are_fed_and_gated() -> None:
    stats = OppStats()
    st = hand_with_history([])
    st.apply(MatchInfo(hands=400, sb=1, bb=2, stack=200))
    for _ in range(GATE + 5):
        st.apply(HandStart(1, 0, 200, 200))
        st.record_my_action(Action.raise_to(5))
        msg = OppAction(Action.fold())
        st.apply(msg)
        stats.update(st, msg)
    assert stats.spots["fold_to_open"].n == GATE + 5 and stats.spots["three_bet"].hits == 0
    assert stats.tilt("fold_to_open") > 0 and stats.rate("fold_to_open") <= POPULATION["fold_to_open"] + CAP + 1e-9
    assert stats.tilt("three_bet") < 0 and stats.rate("three_bet") >= 0.0
    fresh = OppStats()
    assert fresh.tilt("cbet") == 0.0 and fresh.rate("cbet") == POPULATION["cbet"]
