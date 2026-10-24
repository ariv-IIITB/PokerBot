"""Phase 12: deck plugin and every evaluator plugin vs slow brute-force references.

Fast tests use a few thousand random cases each; the `slow` versions use >= 50k.
"""
import numpy as np
import pytest
from reference_eval import (ref_best_general, ref_high_key, ref_low_27_key, ref_low_a5_key,
                            ref_shares, ref_wild_key)

from bot.cards import parse_cards as P
from bot.evaluator import (FIVE_KIND, FLUSH, NOT_QUALIFIED, STRAIGHT,
                           STRAIGHT_FLUSH, HandEvaluator, category, order_from_names)
from bot.game.compile import build_evaluator, compile_spec
from bot.game.deck import Deck
from bot.game.scoring import Scorer, split_pot
from variant.spec import VariantSpec, load_catalog

SHORT = Deck(ranks="6789TJQKA")
SHORT_ORDER = ["high_card", "pair", "two_pair", "trips", "straight", "full_house", "flush",
               "quads", "straight_flush"]


def same_order(values, refs) -> None:
    """Evaluator values must induce exactly the reference ordering, ties included.
    Reference None (not qualified) must map to NOT_QUALIFIED."""
    ref_to_val: dict = {}
    for r, v in zip(refs, values):
        if r is None:
            assert v == NOT_QUALIFIED, (r, v)
            continue
        assert ref_to_val.setdefault(r, v) == v, f"same reference hand, different values: {r}"
    pairs = sorted(ref_to_val.items())
    vals = [v for _, v in pairs]
    assert vals == sorted(vals) and len(set(vals)) == len(vals), "ordering mismatch"


def deals(n, size, deck=tuple(range(52)), seed=0, share_board_from=None):
    rng = np.random.default_rng(seed)
    d = np.array(deck)
    out = d[np.argsort(rng.random((n, len(d))), axis=1)[:, :size]]
    return out


def run_case(ev, n, n_hole, n_board, keyfn, deck=tuple(range(52)), seed=0, **refkw) -> None:
    ds = deals(n, n_hole + n_board, deck, seed)
    # Reuse boards for half the hands so ties are common.
    ds[1::2, n_hole:] = ds[0::2, n_hole:][: len(ds[1::2])]
    ds = ds[[len(set(x)) == len(x) for x in ds.tolist()]]
    vals = ev.evaluate_batch(ds[:, :n_hole], ds[:, n_hole:]).tolist()
    scal = [ev.evaluate(d[:n_hole], d[n_hole:]) for d in ds[:300].tolist()]
    assert scal == vals[:300], "scalar and batch disagree"
    refs = [ref_best_general(d[:n_hole], d[n_hole:], keyfn, **refkw) for d in ds.tolist()]
    same_order(vals, refs)


# --------------------------------------------------------------------------- deck plugin

def test_deck_plugin() -> None:
    assert Deck().is_standard_52 and len(SHORT) == 36
    assert len(Deck(jokers=2)) == 54 and len(Deck(copies=2)) == 104
    assert len(Deck(removed=("Ah", "As"))) == 50
    assert SHORT.pos_high[P("6c")[0]] == 0 and SHORT.pos_high[P("As")[0]] == 8
    assert Deck().pos_ace_low[P("Ah")[0]] == 0 and Deck().pos_ace_low[P("2h")[0]] == 1
    j = Deck(jokers=1)
    assert j.joker[52] and j.suit[52] == -1
    two = Deck(copies=2)
    assert two.cards[52] == 64 and two.text([64, 65]) == "2c~1,2d~1"
    with pytest.raises(ValueError):
        Deck(suits="cdhsx")


# --------------------------------------------------------------------------- edge cases

def val(ev, hole, board="-"):
    return ev.evaluate(P(hole), P(board))


def test_short_deck_straights_and_order() -> None:
    ev = HandEvaluator(5, deck=SHORT, order=order_from_names(SHORT_ORDER))
    wheel = val(ev, "Ah,6d", "7c,8s,9h,Kd,Kc")
    assert category(wheel) == order_from_names(SHORT_ORDER)[STRAIGHT]
    assert wheel < val(ev, "Th,6d", "7c,8s,9h,Kd,2c".replace(",2c", ",Qc"))   # 6-T beats A-9
    flush = val(ev, "Ah,Th", "7h,8h,9h,Kd,Kc")
    boat = val(ev, "Kh,Ks", "Kd,8h,8c,6d,7c")
    assert flush > boat                                    # flush beats full house


def test_low_a5() -> None:
    ev = HandEvaluator(5, mode="low_a5", qualifier="8")
    best = val(ev, "Ah,2d,3c,4s,5h")
    assert best > val(ev, "Ah,2d,3c,4s,6h") > val(ev, "8h,7d,5c,4s,3h")
    assert val(ev, "9h,5d,4c,3s,2h") == NOT_QUALIFIED     # 9-high doesn't qualify
    assert val(ev, "Ah,Ad,3c,4s,5h") == NOT_QUALIFIED     # a pair doesn't qualify
    flushy = val(ev, "Ah,2h,3h,4h,5h")
    assert flushy == best                                  # flushes/straights ignored


def test_low_27() -> None:
    ev = HandEvaluator(5, mode="low_27")
    best = val(ev, "7h,5d,4c,3s,2h")
    assert best > val(ev, "8h,5d,4c,3s,2h")
    assert val(ev, "Ah,2d,3c,4s,5h") < val(ev, "Kh,5d,4c,3s,2h")   # A2345 = ace high
    assert val(ev, "6h,5d,4c,3s,2h") < val(ev, "Kh,Qd,Jc,9s,8h")   # straight is bad
    assert val(ev, "7h,5h,4h,3h,2h") < best                        # flush is bad


def test_wilds() -> None:
    deuces = [c for c in range(52) if c // 4 == 0]
    ev = HandEvaluator(5, wild_ids=deuces)
    sf = val(ev, "2c,Kh", "Qh,Jh,Th,4c,7d")            # deuce completes a royal flush
    assert category(sf) == STRAIGHT_FLUSH
    five = val(ev, "2c,2d", "2h,2s,Ah,4c,7d")          # four deuces + ace = five aces
    assert category(five) == FIVE_KIND and five > sf
    assert category(val(ev, "2c,7h", "8h,9h,Jh,3c,3d")) == STRAIGHT_FLUSH  # 2 = Th
    assert category(val(ev, "2c,7h", "8h,9h,Kh,3c,3d")) == FLUSH           # 2 = Ah
    jokers = HandEvaluator(5, deck=Deck(jokers=2), wild_ids=[52, 53])
    assert category(jokers.evaluate([52, 53], P("Ah,Ad,Ac"))) == FIVE_KIND


def test_hole_min_max_and_select_size() -> None:
    at_most_1 = HandEvaluator(5, hole_max=1)
    assert category(val(at_most_1, "Ah,2c", "Kh,Qh,Jh,Th,3d")) == STRAIGHT_FLUSH   # A + board
    assert category(val(at_most_1, "Ah,Kh", "Qh,Jh,Th,2c,3d")) != STRAIGHT_FLUSH   # needs both
    at_least_2 = HandEvaluator(5, hole_min=2)
    assert category(val(at_least_2, "2c,3d", "Ah,Kh,Qh,Jh,Th")) != STRAIGHT_FLUSH
    seven = HandEvaluator(5, hole_exact=2, select_size=7)    # 2 hole + 5 board, best 5 of 7
    assert len(seven.combos(4, 5)) == 1 + 4 * 5 + 6 * 10   # 5-subsets using <= 2 hole cards


def test_hilo_and_boards_shares() -> None:
    hi = HandEvaluator(5, hole_exact=2)
    lo = HandEvaluator(5, hole_exact=2, mode="low_a5", qualifier="8")
    sc = Scorer(high=hi, low=lo)
    board = P("2h,3d,7c,Kd,Ks")
    # P0: A4 makes the nut low; P1: KQ makes trips: split.
    assert sc.shares([P("Ah,4c,Js,Jd"), P("Kc,Qh,9s,9d")], [board]) == [0.5, 0.5]
    # No qualifying low on this board: the high scoops.
    board2 = P("Jh,Td,9c,Kd,Ks")
    assert sc.shares([P("Ah,4c,Js,Jd"), P("Kc,Qh,9s,9d")], [board2]) == [0.0, 1.0]
    # Two boards: split per board.
    hs = Scorer(high=HandEvaluator(5))
    assert hs.shares([P("Ah,Ad"), P("Kh,Kd")], [P("2c,3c,7d,8s,9h"), P("Kc,3h,7s,8d,Jh")]) == [0.5, 0.5]


def test_split_pot_integers() -> None:
    assert split_pot(10, [0.5, 0.5]) == [5, 5]
    assert sum(split_pot(7, [0.25, 0.75])) == 7
    assert split_pot(3, [0.5, 0.5]) == [1, 2]            # odd chip to the big blind


def test_custom_score_hook() -> None:
    spec = VariantSpec.from_dict({"evaluation": {"kind": "score", "score": "hole_rank_sum"}})
    sc = build_evaluator(spec)
    assert sc.evaluate(P("Ah,Kd"), ()) > sc.evaluate(P("2h,3d"), ())
    assert sc.evaluate_batch(np.array([P("Ah,Kd")]), np.zeros((1, 0), int)).tolist() == [23]


def test_catalog_scorers_compile() -> None:
    cat = load_catalog()
    for name in ("short_deck", "deuces_wild", "omaha_hilo", "joker_holdem"):
        r = compile_spec(cat[name])
        assert r.evaluator.evaluate(list(r.deck[:2]), list(r.deck[10:15])) >= NOT_QUALIFIED


# --------------------------------------------------------------------------- randomized vs reference

CASES = {
    "high_7": (lambda: HandEvaluator(5), 2, 5, lambda c: ref_high_key(c), {}),
    "short_order": (lambda: HandEvaluator(5, deck=SHORT, order=order_from_names(SHORT_ORDER)),
                    2, 5, lambda c: ref_high_key(c, "6789TJQKA", order=SHORT_ORDER), {"deck": SHORT.cards}),
    "low_a5_q8": (lambda: HandEvaluator(5, mode="low_a5", qualifier="8"), 2, 5,
                  lambda c: ref_low_a5_key(c, "8"), {}),
    "low_a5": (lambda: HandEvaluator(5, mode="low_a5"), 5, 0, lambda c: ref_low_a5_key(c), {}),
    "low_27": (lambda: HandEvaluator(5, mode="low_27"), 5, 2, ref_low_27_key, {}),
    "omaha_exact2": (lambda: HandEvaluator(5, hole_exact=2), 4, 5, lambda c: ref_high_key(c),
                     {"exact": 2}),
    "hole_min1_max2": (lambda: HandEvaluator(5, hole_min=1, hole_max=2), 3, 5,
                       lambda c: ref_high_key(c), {"lo": 1, "hi": 2}),
    "select7": (lambda: HandEvaluator(5, hole_exact=3, select_size=6), 4, 4,
                lambda c: ref_high_key(c), {"exact": 3, "select": 6}),
}


def _run(name, n, seed) -> None:
    make, n_hole, n_board, keyfn, extra = CASES[name]
    extra = dict(extra)
    deck = extra.pop("deck", tuple(range(52)))
    run_case(make(), n, n_hole, n_board, keyfn, deck, seed, **extra)


@pytest.mark.parametrize("name", sorted(CASES))
def test_random_vs_reference_fast(name) -> None:
    _run(name, 1500, 1)


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(CASES))
def test_random_vs_reference_slow(name) -> None:
    _run(name, 55_000, 2)


def wild_cases(n, seed, n_cards=5, deck_wild="deuces"):
    rng = np.random.default_rng(seed)
    if deck_wild == "deuces":
        wild = [c for c in range(52) if c // 4 == 0]
        deck = list(range(52))
    else:
        wild = [52, 53]
        deck = list(range(54))
    ev = HandEvaluator(5, deck=Deck(jokers=2) if deck_wild == "jokers" else None, wild_ids=wild)
    hands = np.array(deck)[np.argsort(rng.random((n, len(deck))), axis=1)[:, :n_cards]]
    vals = ev.evaluate_batch(hands[:, :2], hands[:, 2:]).tolist()
    refs = []
    ws = set(wild)
    for h in hands.tolist():
        refs.append(max(ref_wild_key([h[i] for i in sub], [h[i] in ws for i in sub])
                        for sub in __import__("itertools").combinations(range(n_cards), 5)))
    scal = [ev.evaluate(h[:2], h[2:]) for h in hands[:200].tolist()]
    assert scal == vals[:200]
    same_order(vals, refs)


@pytest.mark.parametrize("kind", ["deuces", "jokers"])
def test_wild_vs_reference_fast(kind) -> None:
    wild_cases(1500, 3, deck_wild=kind)


@pytest.mark.slow
@pytest.mark.parametrize("kind", ["deuces", "jokers"])
def test_wild_vs_reference_slow(kind) -> None:
    wild_cases(50_000, 4, deck_wild=kind)


def shares_cases(n, seed, n_boards=1, hilo=True) -> None:
    rng = np.random.default_rng(seed)
    hi = HandEvaluator(5, hole_exact=2)
    lo = HandEvaluator(5, hole_exact=2, mode="low_a5", qualifier="8")
    sc = Scorer(high=hi, low=lo if hilo else None)
    for _ in range(n):
        cards = rng.permutation(52)[: 8 + 5 * n_boards].tolist()
        holes = [cards[0:4], cards[4:8]]
        boards = [cards[8 + 5 * b: 13 + 5 * b] for b in range(n_boards)]
        keys = []
        for board in boards:
            comps = [[ref_best_general(h, board, lambda c: ref_high_key(c), exact=2) for h in holes]]
            if hilo:
                comps.append([ref_best_general(h, board, lambda c: ref_low_a5_key(c, "8"), exact=2)
                              for h in holes])
            keys.append(comps)
        assert sc.shares(holes, boards) == pytest.approx(ref_shares(keys))


def test_shares_vs_reference_fast() -> None:
    shares_cases(300, 5, n_boards=1)
    shares_cases(150, 6, n_boards=3)
    shares_cases(150, 7, n_boards=2, hilo=False)


@pytest.mark.slow
def test_shares_vs_reference_slow() -> None:
    shares_cases(25_000, 8, n_boards=1)
    shares_cases(25_000, 9, n_boards=2)
