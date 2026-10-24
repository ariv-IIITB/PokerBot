"""Benchmark every evaluator plugin: single and batched evaluations per second.

A PIMC rollout needs (players x pot components x boards) evaluations. The target is
2,000 rollouts in 20 ms; evaluators below that are flagged.

Usage: .venv/bin/python -m lab.bench_evaluator
"""
from __future__ import annotations

import time

import numpy as np

from bot.evaluator import HandEvaluator, order_from_names, tables
from bot.game.deck import Deck
from bot.game.scoring import CustomEvaluator, SCORES

SHORT = Deck(ranks="6789TJQKA")
SHORT_ORDER = ["high_card", "pair", "two_pair", "trips", "straight", "full_house", "flush",
               "quads", "straight_flush"]
DEUCES = [c for c in range(52) if c // 4 == 0]

# label, evaluator factory, hole, board, deck cards, evaluations per rollout
CASES = [
    ("holdem 7 cards", lambda: HandEvaluator(5), 2, 5, range(52), 2),
    ("holdem flop (5)", lambda: HandEvaluator(5), 2, 3, range(52), 2),
    ("short deck + order", lambda: HandEvaluator(5, deck=SHORT, order=order_from_names(SHORT_ORDER)),
     2, 5, SHORT.cards, 2),
    ("omaha must-use-2", lambda: HandEvaluator(5, hole_exact=2), 4, 5, range(52), 2),
    ("omaha hi-lo (2 comps)", lambda: HandEvaluator(5, hole_exact=2, mode="low_a5", qualifier="8"),
     4, 5, range(52), 4),
    ("A-5 low 7 cards", lambda: HandEvaluator(5, mode="low_a5"), 2, 5, range(52), 2),
    ("2-7 low 5 cards", lambda: HandEvaluator(5, mode="low_27"), 5, 0, range(52), 2),
    ("deuces wild 7 cards", lambda: HandEvaluator(5, wild_ids=DEUCES), 2, 5, range(52), 2),
    ("jokers wild 7 cards", lambda: HandEvaluator(5, deck=Deck(jokers=2), wild_ids=[52, 53]),
     2, 5, Deck(jokers=2).cards, 2),
    ("3 boards (x3)", lambda: HandEvaluator(5), 2, 5, range(52), 6),
    ("custom score", lambda: CustomEvaluator(SCORES["best_heart"], Deck()), 2, 5, range(52), 2),
]
TARGET_ROLLOUTS_PER_S = 2000 / 0.020


def main() -> None:
    t = time.perf_counter()
    tables(5)
    print(f"5-card table build (one-off, at first use): {(time.perf_counter() - t) * 1e3:.1f} ms")
    rng = np.random.default_rng(0)
    print(f"{'evaluator':<24}{'single/s':>10}{'batch1000/s':>13}{'rollouts/20ms':>15}")
    for label, make, h, b, deck, evals_per_rollout in CASES:
        ev = make()
        t = time.perf_counter()
        if hasattr(ev, "warm_up"):
            ev.warm_up()
        build = time.perf_counter() - t
        d = np.array(list(deck))
        deals = d[np.argsort(rng.random((20_000, len(d))), axis=1)[:, :h + b]]
        hole, board = deals[:, :h], deals[:, h:]
        rows = deals[:2000].tolist()
        t = time.perf_counter()
        for r in rows:
            ev.evaluate(r[:h], r[h:])
        single = len(rows) / (time.perf_counter() - t)
        ev.evaluate_batch(hole[:1000], board[:1000])
        t = time.perf_counter()
        for i in range(10):
            ev.evaluate_batch(hole[i * 1000:(i + 1) * 1000], board[i * 1000:(i + 1) * 1000])
        batch = 10_000 / (time.perf_counter() - t)
        rollouts = batch / evals_per_rollout * 0.020
        flag = "" if rollouts >= 2000 else "   <-- below 2,000 rollouts/20 ms"
        extra = f"  (table build {build * 1e3:.0f} ms)" if build > 0.05 else ""
        print(f"{label:<24}{single:>10,.0f}{batch:>13,.0f}{rollouts:>15,.0f}{flag}{extra}")


if __name__ == "__main__":
    main()
