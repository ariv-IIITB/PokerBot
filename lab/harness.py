"""Duplicate-match harness.

For every seed, A and B play one match, then replay the same deals with seats swapped.
The duplicate pair's result for A is (chips in match 1 + chips in match 2); luck of the
deal mostly cancels, so chips/hand standard errors are computed per pair.

Seeds run in parallel across cores (multiprocessing, `spawn`-safe: workers are top-level
functions and players are rebuilt from picklable PlayerSpecs).

CLI:  .venv/bin/python -m lab.harness tier0 random_legal maniac --seeds 20 --hands 400
      (A = first name, then one duplicate run against each opponent listed)
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import time
from dataclasses import dataclass, field
from typing import Optional, Sequence

from lab.engine import MatchResult, play_match
from lab.players import PlayerSpec
from lab.stats import fmt_pm, mean_se
from variant.rules import DEFAULT_CONFIG, GameConfig


@dataclass
class PairResult:
    seed: int
    a_chips: tuple[int, int]          # A's chips in (match 1, match 2)
    a_scores: tuple[float, float]     # A's match points in each match
    hands: int                        # hands played across both matches
    errors: tuple[int, int]           # (A total, B total) illegal replies
    forfeits: tuple[int, int]         # (A, B) forfeits across both matches
    forfeit_reasons: tuple[str, ...]
    a_worst_s: float
    b_worst_s: float


@dataclass
class DuplicateReport:
    a: str
    b: str
    pairs: list[PairResult] = field(default_factory=list)
    hands_per_match: int = 0
    elapsed_s: float = 0.0

    @property
    def chips_per_hand(self) -> tuple[float, float]:
        """A's mean chips per hand ± SE, computed over duplicate pairs."""
        per_pair = [sum(p.a_chips) / max(1, p.hands) for p in self.pairs]
        return mean_se(per_pair)

    @property
    def match_win_rate(self) -> tuple[float, float]:
        """A's mean match score over all individual matches (win 1, draw 0.5)."""
        return mean_se([s for p in self.pairs for s in p.a_scores])

    @property
    def total_hands(self) -> int:
        return sum(p.hands for p in self.pairs)

    def summary(self) -> str:
        cph, se = self.chips_per_hand
        wr, wse = self.match_win_rate
        errs = (sum(p.errors[0] for p in self.pairs), sum(p.errors[1] for p in self.pairs))
        ffs = (sum(p.forfeits[0] for p in self.pairs), sum(p.forfeits[1] for p in self.pairs))
        rate = self.total_hands / self.elapsed_s if self.elapsed_s else 0.0
        return (f"{self.a} vs {self.b}: {fmt_pm(cph, se, 2)} chips/hand | "
                f"match score {wr:.3f} ± {wse:.3f} over {2 * len(self.pairs)} matches | "
                f"errors A/B {errs[0]}/{errs[1]} | forfeits A/B {ffs[0]}/{ffs[1]} | "
                f"{self.total_hands} hands in {self.elapsed_s:.1f}s ({rate:,.0f}/s)")


def play_pair(a: PlayerSpec, b: PlayerSpec, cfg: GameConfig, seed: int,
              hands: Optional[int], on_illegal: str = "fold",
              time_bank_s: Optional[float] = None) -> PairResult:
    """One duplicate pair. Top-level so multiprocessing can pickle it."""
    m1: MatchResult = play_match([a.build(), b.build()], cfg, seed, hands, on_illegal,
                                 time_bank_s=time_bank_s)
    m2: MatchResult = play_match([b.build(), a.build()], cfg, seed, hands, on_illegal,
                                 time_bank_s=time_bank_s)
    ff_a = int(m1.forfeit == 0) + int(m2.forfeit == 1)
    ff_b = int(m1.forfeit == 1) + int(m2.forfeit == 0)
    return PairResult(
        seed=seed,
        a_chips=(m1.chips[0], m2.chips[1]),
        a_scores=(m1.score(0), m2.score(1)),
        hands=m1.hands_played + m2.hands_played,
        errors=(m1.errors[0] + m2.errors[1], m1.errors[1] + m2.errors[0]),
        forfeits=(ff_a, ff_b),
        forfeit_reasons=tuple(r for r in (m1.forfeit_reason, m2.forfeit_reason) if r),
        a_worst_s=max(m1.worst_decision_s[0], m2.worst_decision_s[1]),
        b_worst_s=max(m1.worst_decision_s[1], m2.worst_decision_s[0]),
    )


def _pair_task(args) -> PairResult:
    return play_pair(*args)


def run_duplicate(a: PlayerSpec, b: PlayerSpec, cfg: GameConfig = DEFAULT_CONFIG,
                  seeds: Sequence[int] = range(10), hands: Optional[int] = None,
                  processes: Optional[int] = None, on_illegal: str = "fold",
                  time_bank_s: Optional[float] = None) -> DuplicateReport:
    """Play every seed as a duplicate pair. processes=1 runs inline (no subprocesses);
    None uses all cores. `cfg` (and its hooks) must be picklable for processes > 1."""
    seeds = list(seeds)
    report = DuplicateReport(a.display, b.display,
                             hands_per_match=hands or cfg.hands_per_match)
    tasks = [(a, b, cfg, s, hands, on_illegal, time_bank_s) for s in seeds]
    t0 = time.perf_counter()
    n_proc = processes or os.cpu_count() or 1
    if n_proc <= 1 or len(tasks) <= 1:
        report.pairs = [_pair_task(t) for t in tasks]
    else:
        with mp.get_context("spawn").Pool(min(n_proc, len(tasks))) as pool:
            report.pairs = pool.map(_pair_task, tasks, chunksize=1)
    report.elapsed_s = time.perf_counter() - t0
    return report


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Duplicate match between two brains.")
    ap.add_argument("a")
    ap.add_argument("b", nargs="+", help="one or more opponents")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--first-seed", type=int, default=0)
    ap.add_argument("--hands", type=int, default=None)
    ap.add_argument("--processes", type=int, default=None)
    ap.add_argument("--bank", type=float, default=None,
                    help="time bank per match in seconds (smaller = faster, weaker brains)")
    ap.add_argument("--subprocess", action="store_true",
                    help="run A as a real subprocess bot (uses `--brain A`)")
    args = ap.parse_args(argv)
    if args.subprocess:
        import sys
        spec_a = PlayerSpec.subprocess([sys.executable, "-m", "bot.main", "--brain", args.a],
                                       label=f"{args.a}(proc)")
    else:
        spec_a = PlayerSpec.brain(args.a)
    for b in args.b:
        rep = run_duplicate(spec_a, PlayerSpec.brain(b),
                            seeds=range(args.first_seed, args.first_seed + args.seeds),
                            hands=args.hands, processes=args.processes, time_bank_s=args.bank)
        print(rep.summary(), flush=True)


if __name__ == "__main__":
    main()
