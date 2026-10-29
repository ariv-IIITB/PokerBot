import time

import numpy as np
import pytest

from bot.cards import parse_cards as P
from bot.equity import (equity, equity_exact, equity_scalar, equity_vectorized,
                        sample_without_replacement)
from variant.spec import EvalSpec, VariantSpec


def rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


def test_river_matches_exact() -> None:
    hole, board = P("Ah,Kd"), P("Qh,Jc,2d,3s,9h")
    exact = equity_exact(hole, board)
    assert exact.samples == 990  # C(45, 2) opponent hands
    mc = equity(hole, board, max_samples=20000, rng=rng(1))
    assert abs(mc.equity - exact.equity) < 4 * mc.stderr


def test_turn_matches_exact_both_versions() -> None:
    hole, board = P("8s,8d"), P("Ts,9s,2c,Kh")
    exact = equity_exact(hole, board)
    vec = equity_vectorized(hole, board, max_samples=20000, rng=rng(2))
    sca = equity_scalar(hole, board, max_samples=3000, rng=rng(3))
    assert abs(vec.equity - exact.equity) < 4 * vec.stderr
    assert abs(sca.equity - exact.equity) < 4 * sca.stderr


def test_exact_simple_cases() -> None:
    # Royal flush on board: everyone ties.
    assert equity_exact(P("2c,3d"), P("Ah,Kh,Qh,Jh,Th")).equity == 0.5
    # Nut hand on the river can't lose (the opponent can only tie with... nothing).
    assert equity_exact(P("Ah,Kh"), P("Qh,Jh,Th,2c,3d")).equity == 1.0


@pytest.mark.parametrize("hand,known", [("Ah,Ad", 0.852), ("Kh,Kd", 0.824),
                                        ("Ah,Kh", 0.670), ("7h,2d", 0.346)])
def test_known_preflop_equities(hand: str, known: float) -> None:
    r = equity(P(hand), (), max_samples=60000, rng=rng(4))
    assert abs(r.equity - known) < max(4 * r.stderr, 0.006), r


def test_seeded_is_deterministic() -> None:
    a = equity(P("Ah,Kd"), P("Qh,Jc,2d"), max_samples=2000, rng=rng(9))
    b = equity(P("Ah,Kd"), P("Qh,Jc,2d"), max_samples=2000, rng=rng(9))
    assert a == b


@pytest.mark.parametrize("fn", [equity_vectorized, equity_scalar])
def test_time_budget_respected(fn) -> None:
    fn(P("Ah,Kd"), (), time_budget_s=0.002, max_samples=10**7, rng=rng())  # warm-up
    t0 = time.perf_counter()
    r = fn(P("Ah,Kd"), (), time_budget_s=0.01, max_samples=10**7, rng=rng())
    elapsed = time.perf_counter() - t0
    assert r.samples > 0
    assert elapsed < 0.03, f"{elapsed * 1000:.1f} ms for a 10 ms budget"


def test_dead_cards_removed() -> None:
    # Hero has the nut flush draw dead: with all other hearts dead, the draw can't hit.
    hole, board = P("Ah,Kh"), P("2h,3h,9c,Td")
    dead = P("4h,5h,6h,7h,8h,9h,Th,Jh,Qh")
    with_dead = equity_exact(hole, board, dead=dead)
    without = equity_exact(hole, board)
    assert with_dead.equity < without.equity


def test_variant_config_omaha() -> None:
    cfg = VariantSpec(hole_cards=4, evaluation=EvalSpec(hole_exact=2))
    r = equity(P("Ah,Ad,Kh,Kd"), (), cfg, max_samples=4000, rng=rng(5))
    assert 0.6 < r.equity < 0.8  # AAKK double-suited is ~70% vs a random Omaha hand


def test_sampler_is_uniform_and_distinct() -> None:
    deck = np.arange(10)
    draws = sample_without_replacement(rng(6), deck, 20000, 3)
    assert all(len(set(row)) == 3 for row in draws[:2000].tolist())
    counts = np.bincount(draws.ravel(), minlength=10) / draws.size
    assert np.allclose(counts, 0.1, atol=0.01)


def test_errors() -> None:
    with pytest.raises(ValueError):
        equity(P("Ah,Kd"), P("2c,3c,4c,5c,6c,7c"))  # board too long
    with pytest.raises(ValueError):
        equity_exact(P("Ah,Kd"), ())  # far too many cases
