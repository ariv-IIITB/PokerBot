"""Benchmark Monte Carlo equity: samples per millisecond for typical spots.

Usage: .venv/bin/python -m lab.bench_equity
"""
from __future__ import annotations

import time

import numpy as np

from bot.cards import parse_cards as P
from bot.equity import equity_scalar, equity_vectorized

SPOTS = [("preflop", "Ah,Kd", "-"), ("flop", "Ah,Kd", "Qh,Jc,2d"),
         ("turn", "Ah,Kd", "Qh,Jc,2d,3s"), ("river", "Ah,Kd", "Qh,Jc,2d,3s,9h")]


def main(budget_s: float = 0.02) -> None:
    rng = np.random.default_rng(0)
    print(f"budget {budget_s * 1000:.0f} ms per call")
    for name, hole, board in SPOTS:
        h, b = P(hole), P(board)
        equity_vectorized(h, b, time_budget_s=budget_s, max_samples=10**7, rng=rng)  # warm-up
        row = []
        for fn in (equity_vectorized, equity_scalar):
            t = time.perf_counter()
            r = fn(h, b, time_budget_s=budget_s, max_samples=10**7, rng=rng)
            e = time.perf_counter() - t
            row.append(f"{fn.__name__.split('_')[1]:<10} {r.samples / (e * 1000):6.1f}/ms "
                       f"({r.samples} samples, {e * 1000:.1f} ms, se {r.stderr:.3f})")
        print(f"{name:<8} " + " | ".join(row))


if __name__ == "__main__":
    main()
