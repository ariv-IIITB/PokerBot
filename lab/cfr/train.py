"""Train MCCFR-lite on the active variant's betting abstraction (offline, resumable).

    .venv/bin/python -m lab.cfr.train --variant variant/active.json --minutes 60 \
        [--buckets 8] [--epsilon 0.05] [--out data/<name>/cfr_strategy.json]

Checkpoints (full solver state) go next to the output every --checkpoint-min minutes and at
the end; rerunning the same command resumes. The exported strategy is the average strategy
quantized to uint8 and pruned (rarely reached / uniform infosets dropped), with the spec
hash, so the CFR brain only uses it for the matching variant.
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


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True)
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--buckets", type=int, default=8)
    ap.add_argument("--epsilon", type=float, default=0.05)
    ap.add_argument("--checkpoint-min", type=float, default=5.0)
    ap.add_argument("--min-weight", type=float, default=50.0, help="prune infosets below this")
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    spec = load_variant(args.variant)
    rules = compile_spec(spec)
    out = Path(args.out or f"data/{spec.name}/cfr_strategy.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    ckpt = out.with_suffix(".ckpt")
    game = AbstractGame(rules, args.buckets)
    solver = MCCFR.load(ckpt, game, args.epsilon) if ckpt.is_file() else MCCFR(game, args.seed, args.epsilon)
    start_it = solver.iterations
    t0 = last = time.perf_counter()
    deadline = t0 + args.minutes * 60
    while time.perf_counter() < deadline:
        solver.iterate(50)
        now = time.perf_counter()
        if now - last > args.checkpoint_min * 60:
            solver.save(ckpt)
            last = now
        rate = (solver.iterations - start_it) / (now - t0)
        print(f"\riterations {solver.iterations:,} ({rate:.0f}/s), infosets {len(solver.regret):,}, "
              f"{(deadline - now) / 60:.1f} min left   ", end="", flush=True)
    solver.save(ckpt)
    table = export_uint8(solver, args.min_weight)
    doc = {"spec_hash": spec_hash(spec), "buckets": args.buckets, "iterations": solver.iterations,
           "table": {k: [int(x) for x in v] for k, v in table.items()}}
    out.write_text(json.dumps(doc))
    print(f"\nexported {len(table):,} of {len(solver.avg):,} infosets to {out} "
          f"({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
