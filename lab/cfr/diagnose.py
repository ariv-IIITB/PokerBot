"""Phase 23 diagnostics for the MCCFR-lite solver (lab only).

    .venv/bin/python -m lab.cfr.diagnose leduc --max-iters 1000000 [--epsilon 0.05]
        exact exploitability of the average strategy at 10^2, 10^3, ... iterations
    .venv/bin/python -m lab.cfr.diagnose visits <checkpoint>
        infoset count and traverser-visit histogram of a training checkpoint
    .venv/bin/python -m lab.cfr.diagnose export <checkpoint> <variant> --kind float --out f.json
        re-export a checkpoint: "uint8" (as shipped), "float" (average strategy, unquantized,
        unpruned), "current" (regret matching, not the average); --min-visits prunes rare spots
    .venv/bin/python -m lab.cfr.diagnose quantization <checkpoint>
        what uint8 rounding and uniform-pruning do to the average strategy
"""
from __future__ import annotations

import argparse
import json
import pickle
import time
from collections import Counter
from typing import Optional

import numpy as np

from lab.cfr.exact import Tree, exploitability
from lab.cfr.leduc import Leduc
from lab.cfr.mccfr import MCCFR


def leduc_curve(max_iters: int, epsilon: float = 0.0, seed: int = 0, solver_cls=MCCFR,
                checkpoints: Optional[list[int]] = None, **kw) -> list[dict]:
    """Exploitability of solver_cls's average strategy on Leduc at each checkpoint."""
    game = Leduc()
    tree = Tree(game)
    solver = solver_cls(game, seed=seed, epsilon=epsilon, **kw)
    marks = checkpoints or [10 ** k for k in range(2, 10) if 10 ** k <= max_iters]
    rows, t0 = [], time.perf_counter()
    for m in marks:
        solver.iterate(m - solver.iterations)
        e = exploitability(tree, solver.average_strategy)
        rows.append({"iterations": solver.iterations, "exploitability": e,
                     "seconds": time.perf_counter() - t0})
        print(json.dumps(rows[-1]), flush=True)
    return rows


def _load(ckpt_path: str) -> dict:
    with open(ckpt_path, "rb") as f:
        return pickle.load(f)


def visit_report(ckpt_path: str) -> dict:
    """Infoset count and traverser-visit histogram of a training checkpoint."""
    d = _load(ckpt_path)
    visits = d.get("visits") or {}
    keys = list(set(d["regret"]) | set(d["avg"]))
    v = np.array([visits.get(k, 0) for k in keys])
    edges = [0, 1, 2, 5, 10, 100, 1000, 10 ** 9]
    hist = {f"{a}-{b - 1}": int(((v >= a) & (v < b)).sum()) for a, b in zip(edges, edges[1:])}
    by_street = Counter(str(k).split("|")[0] for k in keys)
    under10 = Counter(str(k).split("|")[0] for k, n in zip(keys, v) if n < 10)
    return {"iterations": d["iterations"], "infosets": len(keys),
            "pct_visited_lt10": float((v < 10).mean() * 100), "median_visits": float(np.median(v)),
            "histogram": hist, "by_street": dict(sorted(by_street.items())),
            "lt10_by_street": dict(sorted(under10.items()))}


def _rm(r: np.ndarray) -> np.ndarray:
    pos = np.maximum(r, 0.0)
    s = pos.sum()
    return pos / s if s > 0 else np.full(len(r), 1.0 / len(r))


def export_table(d: dict, kind: str, min_visits: int = 0) -> dict:
    """infoset -> weights for one export kind (see module docstring)."""
    visits = d.get("visits") or {}
    out = {}
    if kind == "current":
        for k, r in d["regret"].items():
            if visits.get(k, 0) >= min_visits:
                out[k] = [float(x) for x in _rm(r)]
        return out
    for k, a in d["avg"].items():
        if a.sum() <= 0 or (min_visits and visits.get(k, 0) < min_visits):
            continue
        p = a / a.sum()
        if kind == "float":
            out[k] = [float(x) for x in p]
            continue
        if np.allclose(p, 1.0 / len(p), atol=1e-3):
            continue                                    # as shipped: uniform spots pruned
        q = np.floor(p * 255).astype(np.int32)
        q[np.argmax(p)] += 255 - q.sum()
        out[k] = [int(x) for x in q]
    return out


def quantization_report(ckpt_path: str) -> dict:
    """Effect of the shipped export (uint8 + uniform pruning) on the average strategy."""
    d = _load(ckpt_path)
    weights, l1, pruned_w, kept = [], [], 0.0, 0
    total_w = 0.0
    for k, a in d["avg"].items():
        s = a.sum()
        if s <= 0:
            continue
        p = a / s
        total_w += s
        if np.allclose(p, 1.0 / len(p), atol=1e-3):
            pruned_w += s
            continue
        q = np.floor(p * 255).astype(np.int32)
        q[np.argmax(p)] += 255 - q.sum()
        l1.append(np.abs(q / 255 - p).sum())
        weights.append(s)
        kept += 1
    l1, weights = np.array(l1), np.array(weights)
    return {"infosets": len(d["avg"]), "exported": kept,
            "pct_infosets_pruned": 100 * (1 - kept / max(1, len(d["avg"]))),
            "pct_strategy_weight_pruned": 100 * pruned_w / max(total_w, 1e-12),
            "mean_l1_rounding": float(l1.mean()), "weighted_l1_rounding": float((l1 * weights).sum() / weights.sum()),
            "max_l1_rounding": float(l1.max())}


def write_export(ckpt_path: str, variant: str, kind: str, out: str, min_visits: int = 0,
                 buckets: int = 8, fractions: Optional[dict] = None) -> int:
    from lab.harness import load_variant
    from variant.spec import spec_hash
    d = _load(ckpt_path)
    table = export_table(d, kind, min_visits)
    doc = {"spec_hash": spec_hash(load_variant(variant)), "buckets": buckets,
           "iterations": d["iterations"], "kind": kind, "min_visits": min_visits, "table": table}
    if fractions:
        doc["fractions"] = fractions
    with open(out, "w") as f:
        json.dump(doc, f)
    return len(table)


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    le = sub.add_parser("leduc")
    le.add_argument("--max-iters", type=int, default=10 ** 6)
    le.add_argument("--epsilon", type=float, default=0.0)
    le.add_argument("--seed", type=int, default=0)
    vi = sub.add_parser("visits")
    vi.add_argument("ckpt")
    ex = sub.add_parser("export")
    ex.add_argument("ckpt")
    ex.add_argument("variant")
    ex.add_argument("--kind", choices=("uint8", "float", "current"), default="float")
    ex.add_argument("--min-visits", type=int, default=0)
    ex.add_argument("--buckets", type=int, default=8)
    ex.add_argument("--fractions", nargs="*", default=None)
    ex.add_argument("--out", required=True)
    qu = sub.add_parser("quantization")
    qu.add_argument("ckpt")
    args = ap.parse_args(argv)
    if args.cmd == "leduc":
        leduc_curve(args.max_iters, args.epsilon, args.seed)
    elif args.cmd == "visits":
        print(json.dumps(visit_report(args.ckpt)))
    elif args.cmd == "export":
        from lab.cfr.train import parse_fractions
        n = write_export(args.ckpt, args.variant, args.kind, args.out, args.min_visits,
                         args.buckets, parse_fractions(args.fractions))
        print(f"exported {n} infosets to {args.out}")
    elif args.cmd == "quantization":
        print(json.dumps(quantization_report(args.ckpt)))


if __name__ == "__main__":
    main()
