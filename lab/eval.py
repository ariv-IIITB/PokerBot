"""One CLI for every duplicate experiment: our brain against a pool, same output every time.

    .venv/bin/python -m lab.eval BRAIN[:CONFIG] --pool train|heldout|NAME[,NAME...] --pairs 50
        [--locks on|off] [--variant SPEC] [--hands 400] [--bank 60] [--first-seed 0]
        [--report accounting,profile,stats] [--check-profile] [--out logs/NAME.txt] [--final]
    .venv/bin/python -m lab.eval --compare logs/before.txt logs/after.txt [--target opp3]

BRAIN is a key of lab.players.BRAINS. CONFIG overrides its hyperparameters: inline JSON
('tier2:{"call_margin": 0.05}'), a JSON file path, or the name of an entry in
lab.opps.variants.VARIANTS. --locks off turns the endgame lock off for tier2/tier3 (chips per
hand is then the clean measure); the labels get a "-nolock" suffix.

--pool: "train" and "heldout" read lab/opps/discard_pool.json (Phase F); without that file
"train" is the Hold'em LLM bots opp1..opp4 and "heldout" does not exist. --pool heldout needs
--final: held-out bots are for one last check, never for tuning.

Output: one summary line per opponent (chips/hand ± SE over duplicate pairs, match score), then
the --report blocks. --compare reads two such files and prints the per-opponent difference with
its SE and a keep / drop verdict: keep only if the target improves by more than 2 SE (no target:
the sum over opponents improves) and no opponent drops by more than 2 SE.
"""
from __future__ import annotations

import argparse
import json
import os
import math
import re
import sys
from pathlib import Path
from typing import Optional

from lab.harness import load_variant, run_duplicate
from lab.players import PlayerSpec

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VARIANT = "discard_holdem"   # the competition game (was lab/opps/holdem_100bb.json, the old Hold'em Opps/ rules: runs without --variant silently played Hold'em, where Tier 3 is off)
POOL_FILE = ROOT / "lab" / "opps" / "discard_pool.json"
DEFAULT_TRAIN = ["opp1", "opp2", "opp3", "opp4"]
OPP_CONFIG = {"opp3": {"fold_out": False}}          # opp3 would otherwise fold out when ahead
LOCK_BRAINS = {"tier2", "tier3", "tier3x", "tier4", "tier4lab"}

# Action-profile targets for our brain, in percent: spot -> action kind -> (low, high).
# Style targets from the Part 4 plan; winning matches beats hitting a target.
TARGETS = {
    "pre/open": {"R": (65, 75), "C": (20, 28), "F": (0, 7)},
    "pre/bb_vs_limp": {"R": (35, 45)},
    "pre/vs_raise": {"F": (25, 30), "R": (15, 18)},
    "flop/cbet": {"R": (60, 70)},
    "flop/vs_bet": {"F": (30, 45)},
    "river/bet": {"R": (35, 45)},
    "river/vs_bet": {"F": (40, 50)},
}


# --------------------------------------------------------------------------- specs

def parse_brain(text: str, locks: str = "on") -> PlayerSpec:
    """'tier2', 'tier2:{"k": 1}', 'tier2:file.json' or 'tier2:variant_name' -> PlayerSpec."""
    name, _, conf = text.partition(":")
    cfg: dict = {}
    label = name
    if conf:
        if conf.lstrip().startswith("{"):
            cfg = json.loads(conf)
            label = f"{name}[{conf.strip()}]"
        elif Path(conf).is_file():
            cfg = json.loads(Path(conf).read_text())
            label = f"{name}[{Path(conf).stem}]"
        else:
            from lab.opps.variants import VARIANTS
            if conf not in VARIANTS:
                raise SystemExit(f"unknown config {conf!r} for {name}")
            cfg, label = dict(VARIANTS[conf]), f"{name}[{conf}]"
    if locks == "off" and name in LOCK_BRAINS:
        cfg["lock_enabled"] = False
    if locks == "off":
        label += "-nolock"
    return PlayerSpec.brain(name, cfg or None, label=label)


def resolve_pool(pool: list[str], final: bool) -> list[str]:
    names: list[str] = []
    for item in pool:
        for part in item.split(","):
            if part in ("train", "heldout"):
                names += _pool_file(part, final)
            elif part:
                names.append(part)
    return names


def _pool_file(which: str, final: bool) -> list[str]:
    if which == "heldout" and not final:
        raise SystemExit("--pool heldout needs --final: held-out opponents are never tuned on")
    if POOL_FILE.is_file():
        return list(json.loads(POOL_FILE.read_text())[which])
    if which == "heldout":
        raise SystemExit(f"no held-out opponents: {POOL_FILE} does not exist")
    return list(DEFAULT_TRAIN)


def opponent_spec(name: str, locks: str) -> PlayerSpec:
    if name.startswith("remote:"):              # remote:PORT, a friend's bot on another machine (docs/REMOTE_PLAY.md)
        if not os.environ.get("REMOTE_TOKEN"):
            raise SystemExit("remote opponents need REMOTE_TOKEN set (the secret shared with your friend)")
        port = name.split(":", 1)[1]
        return PlayerSpec.subprocess([sys.executable, "-m", "lab.remote_seat", "--port", port],
                                     label=f"remote{port}", protocol="pokerbots")
    if name == "starter":                       # the organisers' starter bot, over the real protocol
        return PlayerSpec.subprocess([sys.executable, str(ROOT / "lab" / "sparring" / "starter_bot.py")],
                                     label="starter", protocol="pokerbots")
    return PlayerSpec.brain(name, OPP_CONFIG.get(name),
                            label=f"{name}-nolock" if locks == "off" else name)


# --------------------------------------------------------------------------- running

def run_pool(brain: str, pool: list[str], pairs: int, variant: str = DEFAULT_VARIANT,
             hands: int = 400, bank: Optional[float] = None, locks: str = "on",
             report: tuple[str, ...] = (), check_profile: bool = False, first_seed: int = 0,
             processes: Optional[int] = None) -> list[str]:
    """Play `pairs` duplicate pairs against each opponent; returns the output lines."""
    from lab.opps import track
    if any(o.startswith("remote:") for o in pool):
        processes = 1                           # one friend, one port: matches must run one at a time
    a = parse_brain(brain, locks)
    cfg = load_variant(variant)
    want_track = bool(report) or check_profile
    out: list[str] = []
    mine = []
    for opp in pool:
        rep = run_duplicate(a, opponent_spec(opp, locks), cfg,
                            seeds=range(first_seed, first_seed + pairs), hands=hands,
                            processes=processes, time_bank_s=bank, track=want_track)
        out.append(rep.summary())
        print(out[-1], flush=True)
        if want_track:
            merged = track.merge([p.track for p in rep.pairs if p.track])
            mine.append(merged)
            names = {"A": rep.a, "B": rep.b}
            blocks = []
            if "profile" in report:
                blocks.append(track.format_profile(merged, names))
            if "accounting" in report:
                blocks.append(track.format_accounting(merged, names, rep.total_hands, [p.track for p in rep.pairs if p.track]))
            if "lines" in report:
                blocks.append(track.format_lines(merged, names, rep.total_hands, [p.track for p in rep.pairs if p.track]))
            if "stats" in report:
                blocks.append(track.format_stats(merged, names))
            out += blocks
            print("\n".join(blocks), flush=True)
    if check_profile and mine:
        lines = check_profile_lines(track.merge(mine), a.display)
        out += lines
        print("\n".join(lines), flush=True)
    return out


def check_profile_lines(merged: dict, label: str) -> list[str]:
    """Pass/fail per TARGETS spot for our brain (player A), pooled over the opponents."""
    lines = [f"--- profile targets: {label}"]
    for spot, kinds in TARGETS.items():
        counts = merged["A"]["spots"].get(spot, {})
        total = sum(counts.values())
        for kind, (lo, hi) in kinds.items():
            if total < 30:
                lines.append(f"  {spot:16} {kind}: n={total} too few decisions")
                continue
            pct = 100.0 * counts.get(kind, 0) / total
            lines.append(f"  {spot:16} {kind}: {pct:5.1f}%  target {lo}-{hi}%  "
                         f"{'PASS' if lo <= pct <= hi else 'FAIL'}  (n={total})")
    return lines


# --------------------------------------------------------------------------- compare

LINE = re.compile(r"^(?P<a>\S+) vs (?P<b>\S+): (?P<m>[+-][\d.]+) ± (?P<se>[\d.]+) chips/hand")


def parse_summary(path: str | Path) -> dict[str, tuple[float, float]]:
    """opponent -> (chips/hand, SE) from the summary lines of a lab.eval output file."""
    out = {}
    for line in Path(path).read_text().splitlines():
        m = LINE.match(line)
        if m:
            out[m["b"].removesuffix("-nolock")] = (float(m["m"]), float(m["se"]))
    return out


def compare(before: dict, after: dict, target: Optional[str] = None) -> tuple[list[str], bool]:
    """(report lines, keep?) for two parsed result sets."""
    lines, keep = [], True
    shared = [o for o in before if o in after]
    if not shared:
        return ["no opponents in common"], False
    if target and target not in shared:
        return [f"target {target!r} is not in both files"], False
    total, total_var = 0.0, 0.0
    for o in shared:
        (m0, s0), (m1, s1) = before[o], after[o]
        d, se = m1 - m0, math.hypot(s0, s1)
        z = d / se if se else 0.0
        total, total_var = total + d, total_var + se ** 2
        flag = ""
        if z < -2:
            flag, keep = "  DROPPED", False
        elif z > 2:
            flag = "  improved"
        lines.append(f"{o:8} {m0:+.2f} -> {m1:+.2f}  diff {d:+.2f} ± {se:.2f} (z {z:+.1f}){flag}")
    agg_se = math.sqrt(total_var)
    agg_z = total / agg_se if agg_se else 0.0
    lines.append(f"sum      diff {total:+.2f} ± {agg_se:.2f} (z {agg_z:+.1f})")
    if target:
        (m0, s0), (m1, s1) = before[target], after[target]
        z = (m1 - m0) / math.hypot(s0, s1) if math.hypot(s0, s1) else 0.0
        ok = z > 2
        lines.append(f"target {target}: z {z:+.1f} -> {'ok' if ok else 'not improved by 2 SE'}")
        keep = keep and ok
    else:
        keep = keep and total > 0
    lines.append("verdict: " + ("KEEP" if keep else "DROP"))
    return lines, keep


# --------------------------------------------------------------------------- CLI

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Duplicate experiments against an opponent pool.")
    ap.add_argument("brain", nargs="?", help="BRAIN[:CONFIG]")
    ap.add_argument("--pool", nargs="+", default=["train"])
    ap.add_argument("--pairs", type=int, default=50)
    ap.add_argument("--first-seed", type=int, default=0)
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--bank", type=float, default=None, help="time bank per match, seconds")
    ap.add_argument("--locks", choices=("on", "off"), default="on")
    ap.add_argument("--variant", default=DEFAULT_VARIANT, help="catalog name or spec JSON path")
    ap.add_argument("--report", default="", help="comma list: accounting, lines, profile, stats")
    ap.add_argument("--check-profile", action="store_true")
    ap.add_argument("--processes", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--final", action="store_true", help="allow --pool heldout")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--target", default=None, help="opponent the change is aimed at")
    args = ap.parse_args(argv)

    if args.compare:
        lines, keep = compare(parse_summary(args.compare[0]), parse_summary(args.compare[1]),
                              args.target)
        print("\n".join(lines))
        return 0 if keep else 1
    if not args.brain:
        ap.error("a BRAIN is required (or --compare)")
    pool = resolve_pool(args.pool, args.final)
    report = tuple(r for r in args.report.split(",") if r)
    bad = set(report) - {"accounting", "lines", "profile", "stats"}
    if bad:
        ap.error(f"unknown --report {sorted(bad)}")
    lines = run_pool(args.brain, pool, args.pairs, args.variant, args.hands, args.bank,
                     args.locks, report, args.check_profile, args.first_seed, args.processes)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
