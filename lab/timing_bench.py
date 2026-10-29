"""Timing benchmark through the real subprocess path.

Reports: bot startup (process start -> ready, measured separately), total bank used over
a match as the engine sees it, mean and worst single decision, and the projected server
numbers (x slowdown, default 2). Fails (exit 1) if the projection exceeds --max-frac of the
bank (default 0.5, the Phase D rule), or if any single reply took more than --max-reply
seconds (default 0.5) or the bot forfeited.

The bot runs as a subprocess over the real wire format ($POKERBOT_PROTOCOL / --protocol,
default pokerbots); --cmd runs something else, e.g. a packaged `bot.py`. The opponent is any
lab brain, `NAME:{json}` (see lab.eval.parse_brain), `tier2-nolock`, or `starter` (the
organisers' starter bot as a subprocess). Locks are off for tier2 opponents: the lock
shortens matches and hides the real cost.

CLI:  .venv/bin/python -m lab.timing_bench --hands 400 --brain tier2 --opponent maniac
      .venv/bin/python -m lab.timing_bench --hands 1000 --bank 150 --variant discard_holdem
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

from lab.engine import play_match, to_rules
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
    max_frac: float = 0.5      # the projected bank use must stay under this share of the bank
    max_reply_s: float = 0.5   # ...and no single reply may take longer than this

    @property
    def mean_s(self) -> float:
        return self.used_s / max(1, self.decisions)

    @property
    def projected_used_s(self) -> float:
        return self.used_s * self.slowdown

    @property
    def ok(self) -> bool:
        return (not self.forfeit and self.projected_used_s <= self.max_frac * self.bank_s
                and self.worst_s <= self.max_reply_s)

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


def measure_startup(brain: str, repeats: int = 3, cwd=None, protocol: Optional[str] = None,
                    cmd: Optional[list[str]] = None) -> float:
    """Best-of-N wall time for the bot to start, load its brain, and exit at end of match."""
    import os
    from bot.protocol import MatchEnd
    from bot.protocols import get_adapter
    a = get_adapter(protocol)
    env = dict(os.environ, POKERBOT_PROTOCOL=a.name)
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        subprocess.run(cmd or [sys.executable, "-m", "bot.main", "--brain", brain], cwd=cwd or ROOT,
                       input=(a.encode_message(MatchEnd()) + "\n").encode(),
                       capture_output=True, timeout=60, env=env)
        best = min(best, time.perf_counter() - t0)
    return best


def _opponent(spec: str):
    """A player for `spec`: 'starter', 'NAME', 'NAME:json', optionally '-nolock' suffixed."""
    from lab.eval import opponent_spec, parse_brain
    if spec == "starter":
        return opponent_spec(spec, "on").build()
    nolock = spec.endswith("-nolock")
    return parse_brain(spec.removesuffix("-nolock"), "off" if nolock else "on").build()


def run_timing(brain: str = "tier2", opponent: str = "maniac", hands: Optional[int] = None,
               bank_s: Optional[float] = None, slowdown: float = 2.0, seed: int = 0,
               variant: Optional[str] = None, cwd=None, protocol: Optional[str] = None,
               cmd: Optional[list[str]] = None,
               max_frac: float = 0.5, max_reply_s: float = 0.5, lock: bool = False) -> TimingReport:
    """variant: catalog name or spec path; the engine and the bot process both play it.
    cmd: how to launch the bot (default `python -m bot.main --brain BRAIN`); cwd: where.
    lock: leave the endgame lock on. Off by default: the lock turns a won match into check/folds
    and hides what the full strategy costs."""
    spec = DEFAULT_CONFIG
    if variant:
        from lab.harness import load_variant
        spec = load_variant(variant)
    rules = to_rules(spec)
    hands = hands or rules.hands_per_match
    bank = bank_s or rules.time_bank_s
    startup = measure_startup(brain, cwd=cwd, protocol=protocol, cmd=cmd)
    bot = SubprocessPlayer(cmd or [sys.executable, "-m", "bot.main", "--brain", brain], name=brain,
                           brain_config=None if lock else {"lock_enabled": False},
                           cwd=str(cwd) if cwd else None, protocol=protocol)
    m = play_match([bot, _opponent(opponent)], spec, seed=seed, hands=hands, time_bank_s=bank,
                   reply_limit_s=5.0)
    # Bank used = our decisions' wall time as the engine measured it.
    used = bank - m.bank_left[0]
    return TimingReport(startup, m.hands_played, m.decisions[0], bank, used,
                        m.worst_after_first_s[0], m.first_decision_s[0], slowdown,
                        m.forfeit_reason if m.forfeit == 0 else "",
                        max_frac=max_frac, max_reply_s=max_reply_s)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Subprocess timing benchmark.")
    ap.add_argument("--brain", default="tier2")
    ap.add_argument("--opponent", default="maniac")
    ap.add_argument("--hands", type=int, default=None)
    ap.add_argument("--bank", type=float, default=None)
    ap.add_argument("--slowdown", type=float, default=2.0)
    ap.add_argument("--variant", default=None, help="catalog name or spec JSON path")
    ap.add_argument("--protocol", default=None, help="wire format (default: the bot's default)")
    ap.add_argument("--cmd", default=None, help="launch command, e.g. 'python bot.py' (with --cwd)")
    ap.add_argument("--cwd", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--lock", action="store_true", help="leave the bot's endgame lock on")
    ap.add_argument("--max-frac", type=float, default=0.5)
    ap.add_argument("--max-reply", type=float, default=0.5)
    args = ap.parse_args(argv)
    import shlex
    rep = run_timing(args.brain, args.opponent, args.hands, args.bank, args.slowdown,
                     seed=args.seed, variant=args.variant, cwd=args.cwd, protocol=args.protocol,
                     cmd=shlex.split(args.cmd) if args.cmd else None,
                     max_frac=args.max_frac, max_reply_s=args.max_reply, lock=args.lock)
    print(rep.summary())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
