"""Benchmark the generic decision layer (bot/sim) on representative variants.

For every decision of a real match it times: reconstruction, the expected-share estimate
(betting decisions) or the special-step policy (card steps, bids, quotes), and records
samples / rollouts per decision. Budget per decision = --budget (default 20 ms).

Usage: .venv/bin/python -m lab.bench_sim [--hands 60] [--budget 0.02]
"""
from __future__ import annotations

import argparse
import time

import numpy as np

from bot.actions import Action
from bot.brains.base import Brain
from bot.sim.policies import decide_special
from bot.sim.replay import reconstruct
from bot.sim.share import expected_share
from lab.engine import play_match
from lab.players import InProcessPlayer, PlayerSpec
from variant.spec import load_catalog

VARIANTS = ["holdem_nl", "mit2026_discard", "omaha_hilo", "three_boards", "auction_card",
            "draw1", "lowball_27"]


class Bench(Brain):
    def __init__(self, budget: float) -> None:
        self.budget = budget
        self.rows: list[tuple[str, float, float, int]] = []   # kind, recon s, total s, samples
        self.rng = np.random.default_rng(0)

    def decide(self, state, legal, budget_s):
        t0 = time.perf_counter()
        rec = reconstruct(self.rules, state.hand, self.rng)
        t1 = time.perf_counter()
        if legal.can_special:
            stats: dict = {}
            a = decide_special(rec, legal, self.rng, self.budget, stats=stats)
            self.rows.append(("special", t1 - t0, time.perf_counter() - t0, stats.get("rollouts", 0)))
            return a
        r = expected_share(rec, self.rng, self.budget)
        self.rows.append((r.path, t1 - t0, time.perf_counter() - t0, r.samples))
        return Action.call() if legal.call else Action.check()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=60)
    ap.add_argument("--budget", type=float, default=0.02)
    args = ap.parse_args(argv)
    cat = load_catalog()
    print(f"budget {args.budget * 1000:.0f} ms per decision")
    print(f"{'variant':<17}{'kind':<9}{'n':>5}{'recon ms':>10}{'mean ms':>9}{'max ms':>8}"
          f"{'decisions/s':>13}{'samples/dec':>13}")
    for name in VARIANTS:
        b = Bench(args.budget)
        play_match([InProcessPlayer(b), PlayerSpec.brain("calling_station").build()], cat[name],
                   seed=1, hands=args.hands, time_bank_s=1e9)
        for kind in ("fast", "rollout", "special"):
            rows = [r for r in b.rows if r[0] == kind]
            if not rows:
                continue
            rec = np.mean([r[1] for r in rows]) * 1000
            tot = np.array([r[2] for r in rows]) * 1000
            smp = np.mean([r[3] for r in rows])
            print(f"{name:<17}{kind:<9}{len(rows):>5}{rec:>10.2f}{tot.mean():>9.1f}{tot.max():>8.1f}"
                  f"{1000 / tot.mean():>13.1f}{smp:>13.0f}")


if __name__ == "__main__":
    main()
