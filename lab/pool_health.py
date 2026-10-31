"""Health check for the Discard Hold'em opponent pool (Phase F): can each bot finish a match?

    .venv/bin/python -m lab.pool_health [d_name ...] [--pairs 10] [--hands 400] [--vs starter,tier2]
        [--bank 60] [--clock-scale 1.0] [--processes N] [--out logs/pool_health.txt]

Every Opps/discard/<name>/bot.py (as d_<name>) plays duplicate pairs against the opponents in
--vs (the organisers' starter bot, and Tier 2 with the endgame lock on) over the real protocol,
under the real limits: the time bank, a 5 s cap on any single reply, start-up within 5 s.
Per bot and opponent it reports:
  forfeits       crash, closed stdout, bank exhausted, a reply over the cap
  malformed      replies the engine cannot read (stray prints, bad JSON, unknown fields)
  illegal        readable replies that were not legal (the engine would send a notice and correct them)
  max reply      slowest single reply, seconds
  bank used      share of the match time bank spent
  stderr         largest stderr output of one match (the real cap is 64 KB)
  first reply    launch to first reply, seconds (start-up plus first decision; the limit is 5 s)
and a verdict "would forfeit: yes/no". Held-out bots get this check and nothing else.

A second pass with --stress-pairs plays against the starter bot with the clock charging every reply
twice (`--clock-scale 2`, a server twice as slow): the bot sees its bank drain twice as fast through
`time_left_ms`, as it would on a slower machine, and either adapts or would forfeit.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from bot.game.rules_spec import to_rules
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec, SubprocessPlayer, discard_pool_bots

ROOT = Path(__file__).resolve().parent.parent
REPLY_CAP_S = 5.0
STDERR_CAP = 64 * 1024


class ProbePlayer(SubprocessPlayer):
    """A pool bot over the real protocol that also records what the engine would complain about."""

    def __init__(self, name: str, folder: Path, stderr_path: str) -> None:
        self.t_launch = time.perf_counter()
        super().__init__([sys.executable, "bot.py"], str(folder), name, stderr_to=stderr_path,
                         protocol="pokerbots")
        self.first_reply_s: Optional[float] = None
        self.malformed = 0
        self.replies = 0
        self.stderr_path = stderr_path

    def act(self, req, timeout=None):
        out = super().act(req, timeout)
        if self.first_reply_s is None:
            self.first_reply_s = time.perf_counter() - self.t_launch
        self.replies += 1
        if isinstance(out, str):                 # SubprocessPlayer returns the raw text when unreadable
            self.malformed += 1
        return out


@dataclass
class MatchHealth:
    forfeit: bool = False
    reason: str = ""
    malformed: int = 0
    illegal: int = 0
    max_reply_s: float = 0.0
    bank_used_frac: float = 0.0
    stderr_bytes: int = 0
    first_reply_s: float = 0.0
    wall_s: float = 0.0
    hands: int = 0
    chips: int = 0


@dataclass
class Row:
    bot: str
    opp: str
    scale: float = 1.0
    matches: list[MatchHealth] = field(default_factory=list)

    def would_forfeit(self) -> tuple[bool, str]:
        reasons = []
        for m in self.matches:
            if m.forfeit:
                reasons.append(m.reason)
            if m.max_reply_s >= REPLY_CAP_S:
                reasons.append(f"reply {m.max_reply_s:.1f}s >= {REPLY_CAP_S:g}s")
            if m.first_reply_s >= REPLY_CAP_S:
                reasons.append(f"start-up {m.first_reply_s:.1f}s >= {REPLY_CAP_S:g}s")
        return bool(reasons), "; ".join(sorted(set(reasons)))[:160]

    def line(self) -> str:
        ms = self.matches
        ff = sum(m.forfeit for m in ms)
        used = max((m.bank_used_frac for m in ms), default=0.0)
        yes, why = self.would_forfeit()
        verdict = "WOULD FORFEIT (" + why + ")" if yes else "ok"
        opp = self.opp + ("" if self.scale == 1 else f" @{self.scale:g}x")
        return (f"{self.bot:18} vs {opp:12} {len(ms):3d} matches | forfeits {ff} | "
                f"malformed {sum(m.malformed for m in ms)} | illegal {sum(m.illegal for m in ms)} | "
                f"max reply {max((m.max_reply_s for m in ms), default=0):.2f}s | "
                f"bank used max {used:.0%} avg {sum(m.bank_used_frac for m in ms) / max(1, len(ms)):.0%} | "
                f"stderr max {max((m.stderr_bytes for m in ms), default=0)} B | "
                f"first reply {max((m.first_reply_s for m in ms), default=0):.2f}s | {verdict}")


def _opp_spec(name: str) -> PlayerSpec:
    if name == "starter":
        return PlayerSpec.subprocess([sys.executable, str(ROOT / "lab" / "sparring" / "starter_bot.py")],
                                     label="starter", protocol="pokerbots")
    return PlayerSpec.brain(name, label=name)


def play_health_pair(bot: str, opp: str, cfg, seed: int, hands: Optional[int],
                     bank: Optional[float], clock_scale: float) -> list[MatchHealth]:
    """Two matches (seats swapped) of pool bot `bot` against `opp`; returns the bot's health in each."""
    folder = discard_pool_bots()[bot]
    out = []
    for first in (True, False):
        tmp = tempfile.NamedTemporaryFile(prefix="pool_health_", suffix=".err", delete=False)
        tmp.close()
        probe = ProbePlayer(bot, folder, tmp.name)
        other = _opp_spec(opp).build(cfg)
        players = [probe, other] if first else [other, probe]
        me = 0 if first else 1
        t0 = time.perf_counter()
        res = play_match(players, cfg, seed, hands, time_bank_s=bank, clock_scale=clock_scale,
                         reply_limit_s=REPLY_CAP_S)
        wall = time.perf_counter() - t0
        rules_bank = bank if bank is not None else to_rules(cfg).time_bank_s
        h = MatchHealth()
        h.forfeit = res.forfeit == me
        h.reason = res.forfeit_reason if h.forfeit else ""
        h.malformed = probe.malformed
        h.illegal = max(0, res.errors[me] - probe.malformed)
        h.max_reply_s = res.worst_after_first_s[me]      # start-up is reported as first_reply_s
        h.bank_used_frac = max(0.0, 1.0 - res.bank_left[me] / rules_bank) if rules_bank else 0.0
        try:
            h.stderr_bytes = os.path.getsize(tmp.name)
            os.unlink(tmp.name)
        except OSError:
            pass
        h.first_reply_s = probe.first_reply_s or 0.0
        h.wall_s, h.hands, h.chips = wall, res.hands_played, res.chips[me]
        out.append(h)
    return out


def _task(args) -> list[MatchHealth]:
    return play_health_pair(*args)


def check_bot(bot: str, opp: str, cfg, pairs: int, hands: Optional[int], bank: Optional[float],
              clock_scale: float = 1.0, processes: Optional[int] = None) -> Row:
    tasks = [(bot, opp, cfg, s, hands, bank, clock_scale) for s in range(pairs)]
    n = min(processes or os.cpu_count() or 1, len(tasks))
    if n <= 1:
        results = [_task(t) for t in tasks]
    else:
        with mp.get_context("spawn").Pool(n) as pool:
            results = pool.map(_task, tasks, chunksize=1)
    return Row(bot, opp, clock_scale, [m for r in results for m in r])


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Health check of the Discard Hold'em opponent pool.")
    ap.add_argument("bots", nargs="*", help="d_<name> ... (default: every Opps/discard/*/bot.py)")
    ap.add_argument("--pairs", type=int, default=10)
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--vs", default="starter,tier2", help="comma list of opponents")
    ap.add_argument("--variant", default="discard_holdem")
    ap.add_argument("--bank", type=float, default=None, help="time bank per match, seconds")
    ap.add_argument("--clock-scale", type=float, default=1.0, help="charge replies this many times")
    ap.add_argument("--stress-pairs", type=int, default=3,
                    help="pairs vs the starter at --stress-scale (0 = skip the slow-server pass)")
    ap.add_argument("--stress-scale", type=float, default=2.0)
    ap.add_argument("--processes", type=int, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    pool = discard_pool_bots()
    bots = args.bots or list(pool)
    bad = [b for b in bots if b not in pool]
    if bad:
        ap.error(f"unknown pool bots {bad}; known: {sorted(pool)}")
    cfg = load_variant(args.variant)
    lines = []
    for bot in bots:
        for opp in [o for o in args.vs.split(",") if o]:
            row = check_bot(bot, opp, cfg, args.pairs, args.hands, args.bank, args.clock_scale, args.processes)
            lines.append(row.line())
            print(lines[-1], flush=True)
        if args.stress_pairs > 0:
            row = check_bot(bot, "starter", cfg, args.stress_pairs, args.hands, args.bank,
                            args.stress_scale, args.processes)
            lines.append(row.line())
            print(lines[-1], flush=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
