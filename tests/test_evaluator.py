"""Evaluator tests: known hands, rule options, and randomized checks vs the reference."""
import itertools
from collections import Counter

import numpy as np
import pytest
from reference_eval import ref_best

from bot.cards import parse_cards as P
from bot.evaluator import (CATEGORY_NAMES, FLUSH, FULL_HOUSE, HIGH_CARD, STRAIGHT,
                           STRAIGHT_FLUSH, TRIPS, GenericEvaluator, category)
from bot.game.rules_spec import to_rules
from variant.spec import EvalSpec, VariantSpec

EV = GenericEvaluator()


def val(hole: str, board: str, ev: GenericEvaluator = EV) -> int:
    return ev.evaluate(P(hole), P(board))


# --------------------------------------------------------------------------- known hands

@pytest.mark.parametrize("hole,board,cat", [
    ("Ah,Kh", "Qh,Jh,Th,2c,3d", STRAIGHT_FLUSH),
    ("Ah,2d", "3c,4s,5h,9d,9c", STRAIGHT),          # wheel beats the pair of nines
    ("Ah,Ad", "Ac,Kd,Kc,2s,3s", FULL_HOUSE),
    ("2h,7h", "9h,Jh,Kh,Ks,Kd", FLUSH),             # flush beats trips
    ("7h,2d", "9c,Js,Kh,4d,3c", HIGH_CARD),
    ("Ks,Kd", "Kh,2c,7d,9s,Jc", TRIPS),
])
def test_known_categories(hole: str, board: str, cat: int) -> None:
    assert category(val(hole, board)) == cat, CATEGORY_NAMES[category(val(hole, board))]


def test_straight_ordering() -> None:
    wheel = val("Ah,2d", "3c,4s,5h,Kd,9c")
    six_high = val("6h,2d", "3c,4s,5h,Kd,9c")
    broadway = val("Ah,Kd", "Qc,Js,Th,2d,3c")
    assert wheel < six_high < broadway
    assert val("Ah,2h", "3h,4h,5h,Kd,9c") < val("6h,2h", "3h,4h,5h,Kd,9c")  # steel wheel


def test_kickers_and_ties() -> None:
    assert val("Ah,Kd", "Ac,7s,4h,3d,2c") > val("Ah,Qd", "Ac,7s,4h,3d,2c")
    # Board plays: both split.
    assert val("2c,3d", "Ah,Kh,Qh,Jh,Th") == val("4c,5d", "Ah,Kh,Qh,Jh,Th")
    # Kicker beyond the best five doesn't count.
    assert val("Ah,3d", "Ac,Kd,Qs,Jh,9c") == val("Ah,2d", "Ac,Kd,Qs,Jh,9c")


def test_two_pair_with_three_pairs_on_board() -> None:
    # Best two pair is KK QQ with an A kicker... the third pair is dropped.
    a = val("Kh,Kd", "Qh,Qd,2c,2d,As")
    b = val("Kc,Ks", "Qc,Qs,3c,3d,Ah")
    assert a == b


def test_hole_cards_used_omaha_style() -> None:
    omaha = GenericEvaluator(5, hole_cards_used=2)
    hole, board = "Ah,Kh,Qh,Jh", "Th,2c,3d,4s,5c"
    assert category(val(hole, board)) == STRAIGHT_FLUSH   # unrestricted: royal
    v = val(hole, board, omaha)                            # must use exactly 2 hole cards
    assert category(v) == HIGH_CARD                        # no flush/straight with 2+3
    assert len(omaha.combos(4, 5)) == 6 * 10


def test_board_only_rule() -> None:
    board_only = GenericEvaluator(5, hole_cards_used=0)
    assert val("Ah,Ad", "2c,5d,9h,Js,Kc", board_only) == val("3h,4d", "2c,5d,9h,Js,Kc", board_only)


def test_smaller_hand_size() -> None:
    three = GenericEvaluator(3)
    assert category(val("Ah,Ad", "Ac,7s,9d", three)) == TRIPS
    assert category(val("2h,3d", "4c,9s,Jd", three)) == STRAIGHT
    assert category(val("2h,3h", "Ah,9s,Jd", three)) == STRAIGHT_FLUSH  # A-2-3 suited


def test_not_enough_cards() -> None:
    with pytest.raises(ValueError):
        EV.evaluate(P("Ah,Kd"), P("2c,3d"))
    with pytest.raises(ValueError):
        GenericEvaluator(5, hole_cards_used=2).evaluate(P("Ah,Kd"), P("2c,3d"))


def test_bad_hand_size() -> None:
    with pytest.raises(ValueError):
        GenericEvaluator(6)


# --------------------------------------------------------------------------- batch

def test_batch_matches_scalar_and_broadcasts() -> None:
    rng = np.random.default_rng(1)
    deals = np.argsort(rng.random((500, 52)), axis=1)[:, :9]
    for used in (None, 2):
        ev = GenericEvaluator(5, used)
        hole, board = deals[:, :4], deals[:, 4:9]
        batch = ev.evaluate_batch(hole, board)
        assert batch.shape == (500,)
        assert batch.tolist() == [ev.evaluate(h, b) for h, b in zip(hole.tolist(), board.tolist())]
    # One shared board for many hands (1-D board broadcast).
    board = P("Ah,Kh,7d,2c,3s")
    holes = np.array([P("Qh,Jh"), P("Ad,Ac"), P("4d,5d")])
    assert EV.evaluate_batch(holes, board).tolist() == [EV.evaluate(h, board) for h in holes.tolist()]


# --------------------------------------------------------------------------- vs reference

def check_against_reference(n_hands: int, n_hole: int, n_board: int, k: int,
                            used, seed: int) -> None:
    """Values must induce exactly the reference ordering (incl. ties)."""
    ev = GenericEvaluator(k, used)
    rng = np.random.default_rng(seed)
    deals = np.argsort(rng.random((n_hands, 52)), axis=1)[:, :n_hole + n_board]
    # Repeat some boards with new hole cards so ties actually occur.
    deals[1::2, n_hole:] = deals[0::2, n_hole:][: len(deals[1::2])]
    clash = [len(set(d)) != len(d) for d in deals.tolist()]
    deals = deals[~np.array(clash)]
    values = ev.evaluate_batch(deals[:, :n_hole], deals[:, n_hole:]).tolist()
    refs = [ref_best(d[:n_hole], d[n_hole:], k, used) for d in deals.tolist()]

    ref_to_val: dict = {}
    for r, v in zip(refs, values):
        assert ref_to_val.setdefault(r, v) == v, f"same reference hand, different values: {r}"
    ordered = sorted(ref_to_val.items())
    vals = [v for _, v in ordered]
    assert vals == sorted(vals) and len(set(vals)) == len(vals), "ordering mismatch"
    for r, v in ordered:
        assert category(v) == r[0]


SHAPES = [  # (hole, board, k, used)
    (2, 3, 5, None), (2, 4, 5, None), (2, 5, 5, None), (3, 5, 5, None), (4, 5, 5, 2),
    (4, 5, 5, None), (2, 5, 5, 0), (3, 4, 5, 1), (2, 2, 3, None), (2, 3, 4, None),
]


@pytest.mark.parametrize("shape", SHAPES)
def test_random_vs_reference_fast(shape) -> None:
    check_against_reference(1500, *shape, seed=sum(shape[:3]))


@pytest.mark.slow
@pytest.mark.parametrize("shape", SHAPES)
def test_random_vs_reference_slow(shape) -> None:
    check_against_reference(14_000, *shape, seed=100 + sum(shape[:3]))


@pytest.mark.slow
def test_all_5_card_hands_exhaustive() -> None:
    combos = np.array(list(itertools.combinations(range(52), 5)), dtype=np.intp)
    vals = EV.evaluate_batch(combos[:, :2], combos[:, 2:])
    counts = Counter((vals >> 20).tolist())
    expected = {8: 40, 7: 624, 6: 3744, 5: 5108, 4: 10200, 3: 54912, 2: 123552,
                1: 1098240, 0: 1302540}
    assert dict(counts) == expected
    assert len(np.unique(vals)) == 7462  # number of distinct 5-card hand ranks


# --------------------------------------------------------------------------- spec

def test_spec_configures_the_evaluator() -> None:
    ev = to_rules(VariantSpec(hole_cards=4, evaluation=EvalSpec(hole_exact=2))).evaluator.high
    assert ev.hole_cards_used == 2 and ev.hand_size == 5


def test_spec_validation() -> None:
    rules = to_rules(VariantSpec())
    assert rules.board_cards == 5 and len(rules.streets) == 4
    assert VariantSpec(evaluation=EvalSpec(hole_exact=3)).validate()       # 3 of 2 hole cards
    assert VariantSpec(hole_cards=1, streets=[0, 2]).validate()            # too few cards
