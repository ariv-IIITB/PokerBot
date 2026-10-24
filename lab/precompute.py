"""Generic precompute pipeline for a variant (run overnight on reveal day).

    .venv/bin/python -m lab.precompute --variant variant/active.json --out data/<name>/ \
        [--hours 8] [--samples 6000] [--range-top 0.3] [--buckets 0] [--seed 0]

Jobs (each resumable: progress is checkpointed to the output folder, and a rerun continues
where it stopped; --hours stops cleanly when time is up):
  classes        suit-isomorphism classes of the starting hand (169 for Hold'em, 1755 for
                 3-card hands) and the card -> class table
  equity_random  per class: expected showdown share from the first decision, vs a random
                 hand, using the generic share engine (works for any variant)
  equity_range   per class: the same vs the top X% of starting hands (by equity_random)
  buckets        optional: per street, K-means (EMD = L1 on CDFs) over equity histograms
Deterministic for a given seed. Respects a total data-size cap (default 50 MB).
meta.json stores the spec hash; the bot uses the data only for a matching variant.
"""
from __future__ import annotations

import argparse
import json
import time
from math import comb
from pathlib import Path
from typing import Optional

import numpy as np

from bot.game.compile import compile_spec
from bot.protocol import HandStart, HoleCards
from bot.sim.canonical import HandClasses
from bot.sim.replay import reconstruct
from bot.sim.share import expected_share
from bot.state import GameState as BotState
from lab.harness import load_variant
from variant.spec import spec_hash

CHECKPOINT_EVERY = 10


class Progress:
    def __init__(self, label: str, total: int, start: int = 0) -> None:
        self.label, self.total, self.done0, self.t0 = label, total, start, time.perf_counter()

    def show(self, done: int) -> None:
        el = time.perf_counter() - self.t0
        rate = (done - self.done0) / el if el > 0 else 0
        eta = (self.total - done) / rate if rate > 0 else float("inf")
        print(f"\r{self.label}: {done}/{self.total} ({100 * done / self.total:.0f}%), "
              f"ETA {eta / 60:.1f} min   ", end="", flush=True)


def _first_hole_size(spec) -> Optional[int]:
    for s in spec.full_program():
        if s["type"] == "deal_hole":
            return s["n"]
        if s["type"] in ("betting", "choose"):
            return None
    return None


def class_share(rules, rep, samples: int, seed: int, inference=None) -> float:
    """Expected share for hole `rep` at our first decision (we are SB)."""
    st = BotState()
    st.apply(HandStart(0, 0, rules.starting_stack, rules.starting_stack))
    st.apply(HoleCards(tuple(rep)))
    rng = np.random.default_rng(seed)
    rec = reconstruct(rules, st.hand, rng)
    return expected_share(rec, rng, time_budget_s=60.0, max_samples=samples,
                          worlds=max(16, samples // 16), inference=inference).share


class RangeFilter:
    """Duck-typed 'inference': weight 1 for opponent hands in the range, ~0 otherwise."""

    def __init__(self, classes, in_range: np.ndarray, unknown_tokens) -> None:
        self.classes, self.in_range, self.tokens = classes, in_range, unknown_tokens
        self.params = {"min_ess": 0.0}
        self.enabled = True

    def log_weights(self, rec, columns, n, rng):
        opp = 1 - rec.me
        toks = [t for t in rec.state.hole[opp]]
        if not all(t in columns for t in toks):
            return None
        holes = np.stack([columns[t] for t in toks], axis=1)
        ok = self.in_range[self.classes.class_batch(holes)]
        return np.where(ok, 0.0, -30.0)


def run(args) -> dict:
    spec = load_variant(args.variant)
    rules = compile_spec(spec)
    out = Path(args.out or f"data/{spec.name}")
    out.mkdir(parents=True, exist_ok=True)
    meta_path = out / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
    want = spec_hash(spec)
    if meta.get("spec_hash") not in (None, want):
        print("existing data is for a different spec: starting over")
        meta = {}
    meta.update(spec_hash=want, variant=spec.name, seed=args.seed, samples=args.samples)
    meta.setdefault("complete", {})
    deadline = time.perf_counter() + args.hours * 3600 if args.hours else None
    cap = args.cap_mb * 1024 * 1024

    def save_meta():
        meta["files"] = {p.name: p.stat().st_size for p in out.glob("*.npy")}
        meta["total_bytes"] = sum(meta["files"].values())
        meta_path.write_text(json.dumps(meta, indent=2))

    def out_of_time():
        return deadline is not None and time.perf_counter() > deadline

    size = _first_hole_size(spec)
    if size is None:
        print("variant has no hole-card deal before the first decision: nothing to precompute")
        save_meta()
        return meta
    n_combos = comb(len(rules.deck), size)
    if n_combos * 4 > cap:
        raise SystemExit(f"class table would be {n_combos * 4 / 1e6:.0f} MB > cap {args.cap_mb} MB")

    # ---- classes
    t = time.perf_counter()
    hc = HandClasses(rules.deck, size)
    np.save(out / "classes.npy", hc.table)
    np.save(out / "class_counts.npy", np.array(hc.counts, dtype=np.int32))
    np.save(out / "class_reps.npy", np.array(hc.representative, dtype=np.int16))
    meta.update(hole_size=size, n_classes=hc.n_classes)
    meta["complete"]["classes"] = True
    print(f"classes: {hc.n_classes} starting-hand classes ({time.perf_counter() - t:.1f}s)")
    save_meta()

    # ---- equity vs random (resumable)
    def equity_job(name: str, key: str, inference_for) -> bool:
        """Fill <name>.npy class by class; marks meta["complete"][key] when finished."""
        path = out / f"{name}.npy"
        vals = np.load(path) if path.is_file() else np.full(hc.n_classes, np.nan)
        start = int(np.sum(~np.isnan(vals)))
        prog = Progress(name, hc.n_classes, start)
        for i in range(hc.n_classes):
            if not np.isnan(vals[i]):
                continue
            if out_of_time():
                np.save(path, vals)
                print(f"\n{name}: stopped for time at {i}/{hc.n_classes} (rerun to resume)")
                return False
            vals[i] = class_share(rules, hc.representative[i], args.samples,
                                  args.seed * 100003 + i, inference_for(i))
            if i % CHECKPOINT_EVERY == 0:
                np.save(path, vals)
                prog.show(int(np.sum(~np.isnan(vals))))
        np.save(path, vals)
        prog.show(hc.n_classes)
        print()
        meta["complete"][key] = True
        save_meta()
        return True

    if not meta["complete"].get("equity_random") and not equity_job(
            "eq_random", "equity_random", lambda i: None):
        save_meta()
        return meta

    # ---- equity vs top X% range
    if args.range_top > 0 and not meta["complete"].get("equity_range"):
        eq = np.load(out / "eq_random.npy")
        order = np.argsort(-eq)
        counts = np.array(hc.counts)
        cum = np.cumsum(counts[order]) / counts.sum()
        top = order[: int(np.searchsorted(cum, args.range_top)) + 1]
        in_range = np.zeros(hc.n_classes, dtype=bool)
        in_range[top] = True
        meta["range_top"] = args.range_top
        ci = hc.index()
        if not equity_job("eq_range", "equity_range", lambda i: RangeFilter(ci, in_range, None)):
            save_meta()
            return meta

    # ---- optional buckets
    if args.buckets > 0 and not meta["complete"].get("buckets"):
        from lab.buckets import build_buckets
        build_buckets(rules, out, args.buckets, args.seed, samples=args.bucket_samples)
        meta["complete"]["buckets"] = True
    save_meta()
    if meta["total_bytes"] > cap:
        print(f"WARNING: data is {meta['total_bytes'] / 1e6:.1f} MB > cap {args.cap_mb} MB")
    return meta


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Precompute variant tables (resumable).")
    ap.add_argument("--variant", required=True, help="catalog name or spec JSON path")
    ap.add_argument("--out", default=None, help="output folder (default data/<variant name>)")
    ap.add_argument("--hours", type=float, default=0.0, help="stop after this long (0 = no limit)")
    ap.add_argument("--samples", type=int, default=6000, help="share samples per class")
    ap.add_argument("--range-top", type=float, default=0.3)
    ap.add_argument("--buckets", type=int, default=0, help="buckets per street (0 = skip)")
    ap.add_argument("--bucket-samples", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cap-mb", type=float, default=50.0)
    args = ap.parse_args(argv)
    t = time.perf_counter()
    meta = run(args)
    print(f"done in {time.perf_counter() - t:.0f}s: {json.dumps(meta.get('complete'))}, "
          f"{meta.get('total_bytes', 0) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
