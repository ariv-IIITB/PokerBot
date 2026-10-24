"""Timing benchmark through the real subprocess path.

Reports: bot startup (process start -> ready, measured separately), total bank used over
a match as the engine sees it, mean and worst single decision, and the projected server
numbers (x slowdown, default 2). Fails (exit 1) if the projection exceeds the bank.

CLI:  .venv/bin/python -m lab.timing_bench --hands 400 --brain tier2 --opponent maniac
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

from lab.engine import play_match
from lab.players import ROOT, PlayerSpec, SubprocessPlayer
from variant.rules import DEFAULT_CONFIG


@dataclass
class TimingReport:
    startup_s: float
    hands: int
    decisions: int
    bank_s: float
    used_s: float
    worst_s: float             # worst decision excluding the first
    first_s: float             # first decision (overlaps the bot's own start-up)
    slowdown: float
    forfeit: str

    @property
    def mean_s(self) -> float:
        return self.used_s / max(1, self.decisions)

    @property
    def projected_used_s(self) -> float:
        return self.used_s * self.slowdown

    @property
    def ok(self) -> bool:
        return not self.forfeit and self.projected_used_s < self.bank_s

    def summary(self) -> str:
        x = self.slowdown
        return (f"startup {self.startup_s * 1000:.0f} ms (x{x:g}: {self.startup_s * x * 1000:.0f} ms)\n"
                f"{self.hands} hands, {self.decisions} decisions: bank used {self.used_s:.2f}s of "
                f"{self.bank_s:g}s -> projected x{x:g} = {self.projected_used_s:.2f}s "
                f"({100 * self.projected_used_s / self.bank_s:.0f}% of bank)\n"
                f"mean decision {self.mean_s * 1000:.2f} ms, worst {self.worst_s * 1000:.1f} ms "
                f"(projected {self.worst_s * x * 1000:.1f} ms); first decision incl. start-up "
                f"overlap {self.first_s * 1000:.0f} ms"
                + (f"\nFORFEIT: {self.forfeit}" if self.forfeit else ""))


def measure_startup(brain: str, repeats: int = 3) -> float:
    """Best-of-N wall time for the bot to start, load its brain, and exit on ENDMATCH."""
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        subprocess.run([sys.executable, "-m", "bot.main", "--brain", brain], cwd=ROOT,
                       input=b"ENDMATCH\n", capture_output=True, timeout=60)
        best = min(best, time.perf_counter() - t0)
    return best


def run_timing(brain: str = "tier2", opponent: str = "maniac", hands: Optional[int] = None,
               bank_s: Optional[float] = None, slowdown: float = 2.0, seed: int = 0) -> TimingReport:
    hands = hands or DEFAULT_CONFIG.hands_per_match
    bank = bank_s or DEFAULT_CONFIG.time_bank_s
    startup = measure_startup(brain)
    bot = SubprocessPlayer([sys.executable, "-m", "bot.main", "--brain", brain], name=brain)
    m = play_match([bot, PlayerSpec.brain(opponent).build()], seed=seed, hands=hands,
                   time_bank_s=bank)
    # Bank used = our decisions' wall time as the engine measured it.
    used = bank - m.bank_left[0]
    return TimingReport(startup, m.hands_played, m.decisions[0], bank, used,
                        m.worst_after_first_s[0], m.first_decision_s[0], slowdown, m.forfeit_reason if m.forfeit == 0 else "")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Subprocess timing benchmark.")
    ap.add_argument("--brain", default="tier2")
    ap.add_argument("--opponent", default="maniac")
    ap.add_argument("--hands", type=int, default=None)
    ap.add_argument("--bank", type=float, default=None)
    ap.add_argument("--slowdown", type=float, default=2.0)
    args = ap.parse_args(argv)
    rep = run_timing(args.brain, args.opponent, args.hands, args.bank, args.slowdown)
    print(rep.summary())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
