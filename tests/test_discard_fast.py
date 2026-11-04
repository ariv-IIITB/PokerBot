"""Phase E1: the sampled one-card discard (bot/sim/discard.py), the smart rollout discard, and
the discard modes the ablation compares."""
import time

import numpy as np
import pytest

from bot.actions import Action, LegalActions, SpecialOption
from bot.cards import parse_cards as P
from bot.game.rules_spec import to_rules
from bot.protocol import (ActRequest, BoardUpdate, HandStart, HoleCards, MatchInfo, OppAction)
from bot.sim.discard import choose_discard, keep_score, opponent_keeps
from bot.sim.policies import decide_special
from bot.sim.replay import reconstruct
from bot.sim.rollout import _best_discard
from bot.state import GameState
from variant.spec import load_catalog

RULES = to_rules(load_catalog()["discard_holdem"])
DISCARD = LegalActions(special=SpecialOption("discard", ("0", "1", "2")))


def at_discard(hole: str, flop: str):
    """(Reconstruction, legal) at our discard as the button, after limp-check, check-check."""
    st = GameState()
    st.apply(MatchInfo(hands=400, sb=1, bb=2, stack=200))
    st.apply(HandStart(0, 0, 200, 200))
    st.apply(HoleCards(P(hole)))
    pre = ActRequest(3, 1, 199, 198, LegalActions(fold=True, call=True, raise_min=4, raise_max=200),
                     None, 1, 2)
    st.apply(pre)
    st.record_my_action(Action.call())
    st.apply(OppAction(Action.check()))
    st.apply(BoardUpdate(1, P(flop)))
    st.apply(OppAction(Action.check()))
    st.apply(ActRequest(4, 0, 198, 198, LegalActions(check=True, raise_min=2, raise_max=198), None, 0, 0))
    st.record_my_action(Action.check())
    st.apply(ActRequest(4, 0, 198, 198, DISCARD, None, 0, 0))
    return reconstruct(RULES, st.hand, np.random.default_rng(1)), DISCARD


@pytest.mark.parametrize("hole,flop,drop", [
    ("As,Kd,7c", "Ah,7d,2s", "1"),     # the Protocol example: two pair (A, 7) beats a pair of aces
    ("Ah,Kh,2c", "Qh,7h,3d", "2"),     # nut flush draw plus the overs: drop the deuce
    ("9s,9d,Ac", "9h,4c,2d", "2"),     # trips: keep both nines
    ("Kc,Kd,4h", "Ah,Kh,2d", "2"),     # a pair of kings (trips on the board's K): keep the pair
])
def test_the_sampled_discard_picks_the_obvious_drop(hole, flop, drop) -> None:
    rec, legal = at_discard(hole, flop)
    got = choose_discard(rec, legal, np.random.default_rng(3), 0.05)
    assert got == Action.special(drop)


def test_it_stays_inside_a_tiny_budget() -> None:
    rec, legal = at_discard("Kc,Qd,5h", "Ah,7d,2s")
    t0 = time.perf_counter()
    for _ in range(5):
        choose_discard(rec, legal, np.random.default_rng(2), 0.004)
    assert (time.perf_counter() - t0) / 5 < 0.03


def test_the_policy_uses_the_mode_it_is_given() -> None:
    rec, legal = at_discard("As,Kd,7c", "Ah,7d,2s")
    rng = np.random.default_rng(4)
    assert decide_special(rec, legal, rng, 0.03, {"discard_mode": "fast"}) == Action.special("1")
    assert decide_special(rec, legal, rng, 0.03, {"discard_mode": "lowest"}) == Action.special("2")   # 7c
    assert decide_special(rec, legal, rng, 0.03, {"discard_mode": "highest2"}) == Action.special("2")
    got = decide_special(rec, legal, rng, 0.05, {"discard_mode": "pimc", "pimc_worlds": 60})
    assert got.kind == "S" and legal.special.allows(got.choice)


def test_what_the_opponent_keeps() -> None:
    ev = RULES.evaluator
    board = np.array(P("Ah,7d,2s"), dtype=np.intp)
    hole = np.array([P("As,7c,2h"), P("Kc,Qc,Jc"), P("9d,9s,4h"), P("Th,4d,3c")], dtype=np.intp)
    kept = opponent_keeps(ev, hole, board)
    keeps = [sorted(row.tolist()) for row in kept]
    assert keeps[0] == sorted(P("As,7c"))                    # two pair, aces and sevens
    assert keeps[1] == sorted(P("Kc,Qc"))                    # nothing made: the two highest
    assert keeps[2] == sorted(P("9d,9s"))                    # the pair
    assert keeps[3] == sorted(P("Th,4d"))                    # high cards


def test_keep_score_orders_made_hands_then_cards_then_draws() -> None:
    ev, board = RULES.evaluator, P("Ah,7d,2s")
    pair = keep_score(ev, P("As,Kd"), board)                 # pair of aces
    two_pair = keep_score(ev, P("As,7c"), board)
    assert two_pair > pair
    assert keep_score(ev, P("Kc,Qc"), board) > keep_score(ev, P("Kc,Jd"), board)    # higher cards
    assert keep_score(ev, P("Qh,Kh"), P("2h,7h,Ac")) > keep_score(ev, P("Qs,Kd"), P("2h,7h,Ac"))  # flush draw nudge


def test_rollout_discard_keeps_the_best_two() -> None:
    from bot.game.state import GameState as RulesState
    deck = list(range(52))
    st = RulesState(RULES, deck, [200, 200], 0)
    st.hole = [P("As,Kd,7c"), P("2c,3d,4h")]
    st.board = P("Ah,7d,2s")
    assert _best_discard(st, 0, ("0", "1", "2")) == "1"          # drop Kd: keep the two pair
    assert _best_discard(st, 1, ("0", "1", "2")) == "1"          # pair of deuces with the 4 kicker: drop the 3


@pytest.mark.parametrize("hole,flop,drop", [
    ("Ah,Kh,2c", "Qh,7h,3d", "2"),
    ("Kc,Kd,4h", "Ah,Kh,2d", "2"),
])
def test_the_stake_weighted_discard_picks_the_same_obvious_drop(hole, flop, drop) -> None:
    from bot.sim.inference import Inference
    rec, legal = at_discard(hole, flop)
    out: dict = {}
    got = choose_discard(rec, legal, np.random.default_rng(3), 0.05,
                         inference=Inference({"discard_stake": 1.0}), out=out)
    assert got == Action.special(drop) and 0.0 <= min(out["means"].values()) <= max(out["means"].values()) <= 1.5   # (share - 0.5) * (1 + stake) + 0.5
