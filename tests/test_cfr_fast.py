"""C1/C2: the Numba evaluator and the bucket-feature twins (docs/cfr/ABSTRACTION_V1.md section 5).

The runtime computes bucket features with NumPy (bot/abstraction.py), the trainer with Numba
(lab/cfr/fast/buckets.py). They must agree exactly, or trainer and runtime keys differ.
"""
import numpy as np
import pytest

pytest.importorskip("numba")

from bot import abstraction as A                       # noqa: E402
from bot.cards import parse_cards                      # noqa: E402
from bot.game.rules_spec import to_rules               # noqa: E402
from lab.cfr.fast import buckets as B                  # noqa: E402
from lab.cfr.fast import eval7 as E                    # noqa: E402
from lab.harness import load_variant                   # noqa: E402


@pytest.fixture(scope="module")
def ev():
    return to_rules(load_variant("discard_holdem")).evaluator


def _random_hands(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.argsort(rng.random((n, 52)), axis=1)[:, :7].astype(np.int64)


def test_eval7_equals_the_bot_evaluator(ev) -> None:
    hands = _random_hands(100_000, 1)
    assert np.array_equal(E.evaluate7(hands), ev.evaluate_batch(hands[:, :2], hands[:, 2:]))


@pytest.mark.slow
def test_eval7_equals_the_bot_evaluator_on_a_million_hands(ev) -> None:
    hands = _random_hands(1_000_000, 2)
    assert np.array_equal(E.evaluate7(hands), ev.evaluate_batch(hands[:, :2], hands[:, 2:]))


def test_splitmix64_reference_vectors_and_twins() -> None:
    # SplitMix64 from state 0 (Vigna's reference implementation)
    assert A.splitmix_stream(0, 3).tolist() == [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4,
                                                0x06C45D188009454F]
    seed = A.card_seed(1, [5, 40, 17], [8, 30, 51])
    assert np.array_equal(A.splitmix_stream(seed, 500), B.stream(np.uint64(seed), 500))


def test_card_seed_ignores_card_order_and_matches_the_twin() -> None:
    a = A.card_seed(2, [40, 5], [8, 30, 51, 12], [3, 9])
    assert a == A.card_seed(2, [5, 40], [51, 12, 8, 30], [9, 3])
    assert a != A.card_seed(2, [5, 40], [8, 30, 51, 12], [3, 10])
    tw = B.card_seed(2, np.array([5, 40]), np.array([8, 12, 30, 51]), np.array([3, 9]))
    assert int(tw) == a


def _situations(n: int, seed: int):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        d = [int(c) for c in rng.permutation(52)[:11]]
        hole3, opp3, board = d[0:3], d[3:6], d[6:11]
        yield hole3, opp3, board


def _check_twins(ev, n: int, seed: int) -> None:
    for hole3, opp3, board in _situations(n, seed):
        k, x, y = A.flop_features(ev, hole3, board[:3])
        assert (k, x, y) == B.flop_features(hole3, board[:3])
        keep = [sorted(hole3)[i] for i in ((0, 1), (0, 2), (1, 2))[k]]
        dead = [c for c in hole3 if c not in keep] + [opp3[0]]
        assert A.turn_features(ev, keep, board[:4], dead) == B.turn_features(keep, board[:4], dead)
        assert A.river_features(ev, keep, board, dead) == B.river_features(keep, board, dead)


def test_numpy_and_numba_features_are_identical(ev) -> None:
    _check_twins(ev, 120, 3)


@pytest.mark.slow
def test_numpy_and_numba_features_are_identical_on_5000_situations(ev) -> None:
    _check_twins(ev, 5000, 4)


def test_features_order_independent(ev) -> None:
    hole3, _opp, board = next(_situations(1, 5))
    assert A.flop_features(ev, hole3, board[:3]) == A.flop_features(ev, hole3[::-1], board[2::-1])


def test_worked_example_features_are_close_to_the_exact_values(ev) -> None:
    """docs/cfr/ABSTRACTION_V1.md section 6: sampled features vs exact enumeration."""
    btn, bb = parse_cards("As,Kd,7c"), parse_cards("Qh,Qs,3d")
    flop = list(parse_cards("Kh,8d,2c"))
    turn, river = list(parse_cards("5s")), list(parse_cards("Jh"))
    dead = list(parse_cards("7c,3d"))
    k, x, y = A.flop_features(ev, btn, flop)
    assert k == 2 and abs(x - 0.896) < 0.03 and abs(y - 0.804) < 0.04     # keep AK = (1, 2)
    k, x, y = A.flop_features(ev, bb, flop)
    assert [sorted(bb)[i] for i in ((0, 1), (0, 2), (1, 2))[k]] == sorted(parse_cards("Qh,Qs"))
    assert abs(x - 0.784) < 0.03
    x, y = A.turn_features(ev, parse_cards("As,Kd"), flop + turn, dead)
    assert abs(x - 0.890) < 0.03 and abs(y - 0.793) < 0.04
    hs, blk = A.river_features(ev, parse_cards("As,Kd"), flop + turn + river, dead)
    assert abs(hs - 0.8926) < 1e-3 and blk == 0                              # exact on the river


def test_bucket_cells() -> None:
    xc = [0.1 * i for i in range(1, 10)]
    yc = [[0.1 * i for i in range(1, 10)]] * 10
    assert A.grid_bucket(0.05, 0.95, xc, yc) == 9
    assert A.grid_bucket(0.95, 0.05, xc, yc) == 90
    assert A.grid_bucket(0.1, 0.1, xc, yc) == 11              # a value on a cut goes up
    assert A.river_bucket(0.5, 1, [0.04 * i for i in range(1, 25)], ) == 2 * 12 + 1
