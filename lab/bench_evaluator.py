"""Benchmark the hand evaluator: table build time, scalar and batch evaluations/second.

Usage: .venv/bin/python -m lab.bench_evaluator
"""
from __future__ import annotations

import time

import numpy as np

SHAPES = [  # (label, hole, board, hand_size, hole_cards_used)
    ("holdem 7 cards", 2, 5, 5, None),
    ("holdem flop (5)", 2, 3, 5, None),
    ("holdem turn (6)", 2, 4, 5, None),
    ("omaha 4+5, use 2", 4, 5, 5, 2),
]


def main() -> None:
    from bot.evaluator import GenericEvaluator, tables
    t = time.perf_counter()
    tables(5)
    print(f"5-card table build (one-off, at first use): {(time.perf_counter() - t) * 1e3:.1f} ms")

    rng = np.random.default_rng(0)
    for label, h, b, k, used in SHAPES:
        ev = GenericEvaluator(k, used)
        deals = np.argsort(rng.random((50_000, 52)), axis=1)[:, :h + b]
        hole, board = deals[:, :h], deals[:, h:]

        rows = deals[:5000].tolist()
        t = time.perf_counter()
        for r in rows:
            ev.evaluate(r[:h], r[h:])
        scalar = len(rows) / (time.perf_counter() - t)

        out = []
        for bs in (100, 1000, 10_000):
            ev.evaluate_batch(hole[:bs], board[:bs])  # warm caches
            reps = max(1, 50_000 // bs)
            t = time.perf_counter()
            for i in range(reps):
                j = (i * bs) % (50_000 - bs + 1)
                ev.evaluate_batch(hole[j:j + bs], board[j:j + bs])
            out.append(f"B={bs}: {reps * bs / (time.perf_counter() - t):>9,.0f}/s")
        print(f"{label:<18} scalar {scalar:>8,.0f}/s   batch " + "   ".join(out))


if __name__ == "__main__":
    main()
