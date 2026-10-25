"""Train MCCFR-lite on the active variant's betting abstraction (offline, resumable).

    .venv/bin/python -m lab.cfr.train --variant variant/active.json --minutes 60 \
        [--buckets 8] [--epsilon 0] [--fractions H=0.5 P=1.0] [--export-at 30 120] \
        [--out data/<name>/cfr_strategy.json]

Checkpoints (full solver state) go next to the output every --checkpoint-min minutes and at
the end; rerunning the same command resumes. The exported strategy is the average strategy
quantized to uint8 and pruned (rarely reached / uniform infosets dropped), with the spec
hash, so the CFR brain only uses it for the matching variant. --export-at also writes
snapshot exports (<out stem>_<m>min.json) at those minutes of this run (--export-iters:
<out stem>_<n>it.json at those iteration counts), and a progress log
(<out stem>.log.jsonl: iterations, infosets, rate) every minute.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from bot.game.compile import compile_spec
from lab.cfr.abstract_game import AbstractGame
from lab.cfr.mccfr import MCCFR, export_uint8
from lab.harness import load_variant
from variant.spec import spec_hash


def parse_fractions(items) -> dict | None:
    """["H=0.5", "P=1.0"] -> {"H": 0.5, "P": 1.0} (labels must not be F, C or A)."""
    if not items:
        return None
    out = {}
    for it in items:
        label, _, frac = it.partition("=")
        if label in ("F", "C", "A") or not label or "/" in label or "|" in label:
            raise ValueError(f"bad raise label {label!r}")
        out[label] = float(frac)
    return out


def export_doc(solver: MCCFR, spec, buckets: int, fractions, min_weight: float,
               min_visits: int = 0) -> dict:
    table = export_uint8(solver, min_weight, min_visits)
    doc = {"spec_hash": spec_hash(spec), "buckets": buckets, "iterations": solver.iterations,
           "table": {k: [int(x) for x in v] for k, v in table.items()}}
    if fractions:
        doc["fractions"] = fractions
    return doc


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True)
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--buckets", type=int, default=8)
    ap.add_argument("--epsilon", type=float, default=0.0,
                    help="trembling hand; biased if > 0 (see lab/cfr/mccfr.py)")
    ap.add_argument("--fractions", nargs="*", default=None, help="raise sizes, e.g. H=0.5 P=1.0")
    ap.add_argument("--checkpoint-min", type=float, default=5.0)
    ap.add_argument("--export-at", type=float, nargs="*", default=[],
                    help="also export snapshots at these minutes of this run")
    ap.add_argument("--export-iters", type=int, nargs="*", default=[],
                    help="also export snapshots at these iteration counts")
    ap.add_argument("--min-weight", type=float, default=50.0, help="prune infosets below this")
    ap.add_argument("--min-visits", type=int, default=0,
                    help="prune infosets the traverser visited fewer times (bot falls back)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    spec = load_variant(args.variant)
    rules = compile_spec(spec)
    fractions = parse_fractions(args.fractions)
    out = Path(args.out or f"data/{spec.name}/cfr_strategy.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    ckpt = out.with_suffix(".ckpt")
    log_path = out.with_name(out.stem + ".log.jsonl")
    game = AbstractGame(rules, args.buckets, fractions)
    solver = MCCFR.load(ckpt, game, args.epsilon) if ckpt.is_file() else MCCFR(game, args.seed, args.epsilon)
    start_it = solver.iterations
    t0 = last = last_log = time.perf_counter()
    deadline = t0 + args.minutes * 60
    pending = sorted(args.export_at)
    pending_iters = sorted(i for i in args.export_iters if i > solver.iterations)
    while time.perf_counter() < deadline:
        step = 50 if not pending_iters else max(1, min(50, pending_iters[0] - solver.iterations))
        solver.iterate(step)
        now = time.perf_counter()
        if pending_iters and solver.iterations >= pending_iters[0]:
            n = pending_iters.pop(0)
            solver.save(out.with_name(f"{out.stem}_{n}it.ckpt"))
            snap = out.with_name(f"{out.stem}_{n}it.json")
            snap.write_text(json.dumps(export_doc(solver, spec, args.buckets, fractions,
                                                  args.min_weight, args.min_visits)))
        if now - last > args.checkpoint_min * 60:
            solver.save(ckpt)
            last = now
        if pending and now - t0 >= pending[0] * 60:
            m = pending.pop(0)
            solver.save(out.with_name(f"{out.stem}_{m:g}min.ckpt"))
            snap = out.with_name(f"{out.stem}_{m:g}min.json")
            snap.write_text(json.dumps(export_doc(solver, spec, args.buckets, fractions,
                                                  args.min_weight, args.min_visits)))
        rate = (solver.iterations - start_it) / (now - t0)
        if now - last_log >= 60:
            last_log = now
            with open(log_path, "a") as f:
                f.write(json.dumps({"minutes": (now - t0) / 60, "iterations": solver.iterations,
                                    "infosets": len(solver.regret), "rate": rate}) + "\n")
        print(f"\riterations {solver.iterations:,} ({rate:.0f}/s), infosets {len(solver.regret):,}, "
              f"{(deadline - now) / 60:.1f} min left   ", end="", flush=True)
    solver.save(ckpt)
    doc = export_doc(solver, spec, args.buckets, fractions, args.min_weight, args.min_visits)
    out.write_text(json.dumps(doc))
    print(f"\nexported {len(doc['table']):,} of {len(solver.avg):,} infosets to {out} "
          f"({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
