"""Fuzz our bot against weird opponents across example variants.

Asserts (per match): no exception escapes the engine or our bot, our bot sends zero
illegal actions, no forfeits by our bot, and chips are conserved. The weird bots send
random raise sizes (often out of range), min-raise spam, all-in spam and malformed replies,
which the engine must handle (auto check/fold + error count).

CLI:  .venv/bin/python -m lab.fuzz --hands 200000            (spread over all cores)
      .venv/bin/python -m lab.fuzz --hands 2000 --subprocess  (our bot as a real process,
                                                               with junk lines injected)
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import random
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Optional

from bot.protocol import ActRequest
from lab.engine import play_match
from lab.example_variants import EXAMPLES
from lab.players import PlayerSpec, SubprocessPlayer

# A fast setting for our brain so fuzzing covers many hands.
FAST_BRAIN = {"max_samples": 64, "rollout_worlds": 12, "pimc_worlds": 2}
JUNK = ["", "garbage", "ACT pot=x", "HOLE cards=ZZ", "OPP type=Q", "\x00\x01\x02",
        "MATCH hands=-1", "END delta=abc", "BOARD street=1 cards=Ah,Ah", "R 10", "💥"]


class WeirdPlayer:
    """Engine-side opponent that misbehaves in a chosen style."""

    STYLES = ("random_size", "min_raise", "all_in", "malformed", "mixed")

    def __init__(self, style: str, seed: int = 0) -> None:
        self.style = style
        self.rng = random.Random(seed)
        self.name = f"weird:{style}"

    def notify(self, msg) -> None:
        pass

    def act(self, req: ActRequest) -> str:
        style = self.style if self.style != "mixed" else self.rng.choice(self.STYLES[:-1])
        L, r = req.legal, self.rng
        if L.special is not None:
            sp = L.special
            pick = str(r.randint(sp.lo - 3, sp.hi + 3)) if sp.is_range else r.choice(sp.choices)
            return r.choice([f"S {pick}", "S nope", "F"])
        if style == "random_size":
            return r.choice(["F", "K", "C", f"R {r.randint(-50, 2000)}"])
        if style == "min_raise":
            return f"R {L.raise_min}" if L.can_raise else ("C" if L.call else "K")
        if style == "all_in":
            return f"R {L.raise_max}" if L.can_raise else ("C" if L.call else "K")
        return r.choice(["", "X", "R", "R abc", "R 1e9", "F F", "C 3", "raise", "\x00",
                         "K", "C", f"R {L.raise_min}"])

    def close(self) -> None:
        pass


class NoisySubprocessPlayer(SubprocessPlayer):
    """Our bot as a subprocess, with junk lines injected before real messages."""

    def __init__(self, seed: int = 0, **kw) -> None:
        super().__init__(**kw)
        self.rng = random.Random(seed)

    def _send(self, line: str) -> None:
        if self.rng.random() < 0.3:
            super()._send(self.rng.choice(JUNK))
        super()._send(line)


@dataclass
class FuzzReport:
    hands: int = 0
    matches: int = 0
    opp_errors: int = 0
    failures: list[str] = field(default_factory=list)

    def merge(self, other: "FuzzReport") -> None:
        self.hands += other.hands
        self.matches += other.matches
        self.opp_errors += other.opp_errors
        self.failures += other.failures


def fuzz_task(args) -> FuzzReport:
    """Play `matches` matches with one variant and one weird style. Top-level for pickling."""
    variant, style, seed, matches, hands, brain, subprocess_bot = args
    cfg = EXAMPLES[variant]
    rep = FuzzReport()
    for i in range(matches):
        s = seed * 1000 + i
        ours = (NoisySubprocessPlayer(seed=s, cmd=[sys.executable, "-m", "bot.main", "--brain", brain])
                if subprocess_bot else PlayerSpec.brain(brain, FAST_BRAIN).build())
        players = [ours, WeirdPlayer(style, s)]
        me = i % 2
        if me == 1:
            players.reverse()
        tag = f"{variant}/{style}/seed{s}"
        try:
            m = play_match(players, cfg, seed=s, hands=hands, time_bank_s=600.0)
        except Exception:
            rep.failures.append(f"{tag}: exception\n{traceback.format_exc()}")
            continue
        rep.matches += 1
        rep.hands += m.hands_played
        rep.opp_errors += m.errors[1 - me]
        if m.errors[me]:
            rep.failures.append(f"{tag}: our bot sent {m.errors[me]} illegal actions")
        if m.forfeit == me:
            rep.failures.append(f"{tag}: our bot forfeited ({m.forfeit_reason})")
        if m.forfeit is None and m.chips[0] + m.chips[1] != 0:
            rep.failures.append(f"{tag}: chips not conserved {m.chips}")
    return rep


def run_fuzz(total_hands: int = 20000, hands_per_match: int = 100, brain: str = "tier2",
             variants: Optional[list[str]] = None, processes: Optional[int] = None,
             subprocess_bot: bool = False, seed: int = 0) -> FuzzReport:
    variants = variants or list(EXAMPLES)
    combos = [(v, s) for v in variants for s in WeirdPlayer.STYLES]
    matches_total = max(len(combos), total_hands // hands_per_match)
    per_combo = max(1, matches_total // len(combos))
    tasks = [(v, s, seed + k, per_combo, hands_per_match, brain, subprocess_bot)
             for k, (v, s) in enumerate(combos)]
    n_proc = processes or os.cpu_count() or 1
    report = FuzzReport()
    if n_proc <= 1:
        results = [fuzz_task(t) for t in tasks]
    else:
        with mp.get_context("spawn").Pool(min(n_proc, len(tasks))) as pool:
            results = pool.map(fuzz_task, tasks, chunksize=1)
    for r in results:
        report.merge(r)
    return report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Fuzz our bot against weird opponents.")
    ap.add_argument("--hands", type=int, default=20000)
    ap.add_argument("--hands-per-match", type=int, default=100)
    ap.add_argument("--brain", default="tier2")
    ap.add_argument("--variants", nargs="*", default=None, choices=list(EXAMPLES))
    ap.add_argument("--processes", type=int, default=None)
    ap.add_argument("--subprocess", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    rep = run_fuzz(args.hands, args.hands_per_match, args.brain, args.variants,
                   args.processes, args.subprocess, args.seed)
    dt = time.perf_counter() - t0
    print(f"{rep.hands:,} hands in {rep.matches} matches, {dt:.1f}s ({rep.hands / dt:,.0f}/s); "
          f"opponent illegal replies handled: {rep.opp_errors:,}; failures: {len(rep.failures)}")
    for f in rep.failures[:20]:
        print("FAIL", f)
    return 1 if rep.failures else 0


if __name__ == "__main__":
    sys.exit(main())
