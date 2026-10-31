"""Train the v1 blueprint (build map C3/C4; lab only).

    .venv/bin/python -m lab.cfr.fast.train --pool data/cfr/pool_v1.npz --hours 2 --threads 10 \
        --out data/cfr/run1 [--resume] [--lcfr-batches 40] [--batch 20000000]

Every batch: a progress line (iterations, it/s, share of rows the traverser visited fewer than 10
times, per street). Every --checkpoint-min minutes and at the end: <out>/checkpoint.npz (resume
with --resume) and <out>/blueprint_v1.npz (the export of docs/cfr/ABSTRACTION_V1.md section 3).
With --exploit N, also the exploitability inside the abstraction on N pool deals (an estimate:
a best response on a sample of deals is optimistic).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from lab.cfr.fast import deals as D
from lab.cfr.fast import mccfr, tree

N_BUCKETS = (1755, 100, 100, 50)
VERSION = "v1"


def load_game(pool_path: str, cuts_path: str, variant: str = "discard_holdem",
              limit: int = 0) -> tuple[mccfr.Game, dict, tree.Params]:
    par = tree.Params.from_variant(variant)
    flat = tree.flatten(par)
    pool = np.load(pool_path)
    feats, sd = pool["feats"], pool["sd"]
    if limit:
        feats, sd = feats[:limit], sd[:limit]
    cuts = json.loads(Path(cuts_path).read_text())
    game = mccfr.Game.from_flat(flat, N_BUCKETS, D.bucket_ids(feats, cuts), sd)
    return game, cuts, par


def coverage(game: mccfr.Game, visits: np.ndarray, below: int = 10) -> list[float]:
    """Per street: share of rows visited fewer than `below` times."""
    out = []
    for st in range(len(game.n_buckets)):
        lo = game.offset[st]
        hi = game.offset[st + 1] if st + 1 < len(game.offset) else game.rows
        out.append(float(np.mean(visits[lo:hi] < below)))
    return out


def blueprint_meta(game: mccfr.Game, cuts: dict, par: tree.Params, variant: str,
                   iterations: int, min_visits: int) -> dict:
    from lab.harness import load_variant
    from variant.spec import spec_hash
    return {"version": VERSION, "spec_hash": spec_hash(load_variant(variant)),
            "params": dataclasses.asdict(par), "n_buckets": list(N_BUCKETS),
            "offset": game.offset.tolist(), "rows": game.rows, "thresholds": cuts,
            "histories": game.histories, "iterations": int(iterations), "min_visits": min_visits,
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def export(path: Path, trainer: mccfr.Trainer, cuts: dict, par: tree.Params, variant: str,
           min_visits: int) -> dict:
    g = trainer.g
    probs = mccfr.export_uint8(trainer.average(), g, trainer.visits, min_visits)
    meta = blueprint_meta(g, cuts, par, variant, trainer.iterations, min_visits)
    np.savez_compressed(path, probs=probs, meta=json.dumps(meta))
    return {"rows_kept": int((probs.sum(axis=1) > 0).sum()), "bytes": path.stat().st_size}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pool", required=True)
    ap.add_argument("--cuts", default="lab/cfr/fast/cuts_v1.json")
    ap.add_argument("--variant", default="discard_holdem")
    ap.add_argument("--hours", type=float, default=0.0)
    ap.add_argument("--iters", type=int, default=0)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--batch", type=int, default=20_000_000)
    ap.add_argument("--lcfr-batches", type=int, default=40, help="discount t/(t+1) after the first N batches")
    ap.add_argument("--min-visits", type=int, default=10)
    ap.add_argument("--checkpoint-min", type=float, default=15.0)
    ap.add_argument("--exploit", type=int, default=0, help="deals for the exploitability estimate")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    game, cuts, par = load_game(args.pool, args.cuts, args.variant)
    tr = mccfr.Trainer(game, seed=args.seed, threads=args.threads, lcfr_batches=args.lcfr_batches)
    ck = out / "checkpoint.npz"
    if args.resume and ck.is_file():
        tr.load_state(np.load(ck))
        print(f"resumed at {tr.iterations:,} iterations", flush=True)
    log = (out / "progress.log").open("a")

    def say(msg: str) -> None:
        line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    def save() -> None:
        np.savez(ck, **tr.state())
        info = export(out / f"blueprint_{VERSION}.npz", tr, cuts, par, args.variant, args.min_visits)
        say(f"saved checkpoint and blueprint ({info['rows_kept']:,} rows kept, {info['bytes'] / 1e6:.2f} MB)")
        if args.exploit:
            sub = mccfr.Game(**{**game.__dict__, "buckets": game.buckets[: args.exploit],
                                "showdown": game.showdown[: args.exploit]})
            v = mccfr.exact_values(sub, tr.average())
            say(f"exploitability on {args.exploit:,} deals: {v['exploitability']:.3f} chips/hand "
                f"(br0 {v['br0']:+.3f}, br1 {v['br1']:+.3f}, value0 {v['value0']:+.3f})")

    say(f"rows {game.rows:,}, deals {len(game.showdown):,}, threads {args.threads}, batch {args.batch:,}")
    t0 = time.perf_counter()
    last_ck = t0
    start_it = tr.iterations
    deadline = t0 + args.hours * 3600 if args.hours else None
    while True:
        if args.iters and tr.iterations - start_it >= args.iters:
            break
        if deadline and time.perf_counter() >= deadline:
            break
        m = args.batch if not args.iters else min(args.batch, args.iters - (tr.iterations - start_it))
        tb = time.perf_counter()
        tr.train(m, batch=m)
        rate = m / (time.perf_counter() - tb)
        cov = coverage(game, tr.visits)
        say(f"it {tr.iterations:,}  {rate:,.0f} it/s  rows visited < 10x: "
            + " ".join(f"{s}={c:.1%}" for s, c in zip(("pre", "flop", "turn", "river"), cov)))
        if time.perf_counter() - last_ck >= args.checkpoint_min * 60:
            save()
            last_ck = time.perf_counter()
    save()
    log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
