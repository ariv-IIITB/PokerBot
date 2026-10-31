"""The training deal pool and the bucket thresholds (docs/cfr/ABSTRACTION_V1.md sections 4, 5.5, 5.6).

A deal = 3 hole cards per seat and a 5-card board, drawn with SplitMix64 from (pool seed, deal
index), so every pool is reproducible. Per deal and seat the pool stores the exact integer bucket
features (both seats discard by the fixed policy of section 4) and the showdown result; bucket ids
follow from any set of cuts without recomputing anything.

    .venv/bin/python -m lab.cfr.fast.deals --deals 10000000 --out data/cfr/pool_v1.npz
    .venv/bin/python -m lab.cfr.fast.deals --fit 200000 --pool data/cfr/pool_v1.npz --cuts lab/cfr/fast/cuts_v1.json
"""
from __future__ import annotations

import argparse
import json
import time
from math import comb
from pathlib import Path
from typing import Optional

import numpy as np
from numba import njit, prange

from bot.abstraction import FLOP_OPP, FLOP_RUNOUTS, TURN_OPP
from lab.cfr.fast.buckets import U_GOLDEN, flop_counts, mix, river_counts, turn_counts
from lab.cfr.fast.eval7 import TABLES, eval7

# denominators of the features (section 5): flop / turn E[HS], E[HS^2]; river HS
FLOP_DEN = (2 * FLOP_OPP * FLOP_RUNOUTS, (2 * FLOP_OPP) ** 2 * FLOP_RUNOUTS)
TURN_RIVERS = 44                       # 52 - 2 hole - 4 board - 2 discards
TURN_DEN = (2 * TURN_OPP * TURN_RIVERS, (2 * TURN_OPP) ** 2 * TURN_RIVERS)
RIVER_DEN = 2 * comb(43, 2)
KEEPS = ((0, 1), (0, 2), (1, 2))
FIELDS = ("cls", "keep", "f1", "f2", "t1", "t2", "r1", "blk")   # per seat; plus "sd" per deal


def class_table() -> np.ndarray:
    from bot.game.rules_spec import to_rules
    from bot.sim.tables import load_tables
    from lab.harness import load_variant
    t = load_tables(to_rules(load_variant("discard_holdem")))
    if t is None:
        raise RuntimeError("no embedded 3-card class table (data/discard_holdem)")
    return np.ascontiguousarray(t.classes.table, dtype=np.int64)


COMB52 = np.array([[comb(n, j) for j in range(4)] for n in range(53)], dtype=np.int64)


@njit(cache=True)
def class_of(h0, h1, h2, table, comb52):
    """3-card class id (sorted inputs), as bot.sim.canonical.ClassIndex."""
    rest = comb52[51 - h0, 3] + comb52[51 - h1, 2] + comb52[51 - h2, 1]
    return table[comb52[52, 3] - 1 - rest]


@njit(cache=True)
def draw_deal(pool_seed, index, out):
    """11 distinct cards for deal `index` into out: seat 0 hole (3), seat 1 hole (3), board (5)."""
    state = mix(np.uint64(pool_seed) ^ (np.uint64(index) * U_GOLDEN))
    deck = np.arange(52)
    for i in range(11):                         # partial Fisher-Yates
        state = state + U_GOLDEN
        j = i + np.int64(mix(state) % np.uint64(52 - i))
        deck[i], deck[j] = deck[j], deck[i]
        out[i] = deck[i]


@njit(cache=True)
def _sort3(a, b, c):
    if a > b:
        a, b = b, a
    if b > c:
        b, c = c, b
    if a > b:
        a, b = b, a
    return a, b, c


@njit(cache=True, parallel=True)
def build_pool(pool_seed, start, n, table, comb52, comb5, flush5, comb7, multi7):
    """Features of deals start .. start + n - 1: feats (n, 2, 8) int32, showdown (n,) int8."""
    feats = np.empty((n, 2, 8), dtype=np.int32)
    sd = np.empty(n, dtype=np.int8)
    for t in prange(n):
        cards = np.empty(11, dtype=np.int64)
        draw_deal(pool_seed, start + t, cards)
        board = cards[6:11].copy()
        keeps = np.empty((2, 2), dtype=np.int64)
        disc = np.empty(2, dtype=np.int64)
        for p in range(2):
            a, b, c = _sort3(cards[3 * p], cards[3 * p + 1], cards[3 * p + 2])
            hole = np.array([a, b, c], dtype=np.int64)
            feats[t, p, 0] = class_of(a, b, c, table, comb52)
            k, s1, s2 = flop_counts(hole, board[:3].copy(), comb5, flush5, comb7, multi7)
            feats[t, p, 1] = k
            feats[t, p, 2] = s1
            feats[t, p, 3] = s2
            if k == 0:
                keeps[p, 0], keeps[p, 1], disc[p] = a, b, c
            elif k == 1:
                keeps[p, 0], keeps[p, 1], disc[p] = a, c, b
            else:
                keeps[p, 0], keeps[p, 1], disc[p] = b, c, a
        dead = np.sort(disc)
        scratch = np.empty(8, dtype=np.int64)
        v = np.empty(2, dtype=np.int64)
        hand = np.empty(7, dtype=np.int64)
        for p in range(2):
            kp = keeps[p].copy()
            s1, s2, _m = turn_counts(kp, board[:4].copy(), dead, comb5, flush5, comb7, multi7)
            feats[t, p, 4] = s1
            feats[t, p, 5] = s2
            r, _n, blk = river_counts(kp, board, dead, comb5, flush5, comb7, multi7)
            feats[t, p, 6] = r
            feats[t, p, 7] = blk
            hand[0], hand[1] = kp[0], kp[1]
            hand[2:7] = board
            v[p] = eval7(hand, comb5, flush5, comb7, multi7, scratch)
        sd[t] = 1 if v[0] > v[1] else (-1 if v[0] < v[1] else 0)
    return feats, sd


def make_pool(n: int, pool_seed: int = 1, chunk: int = 200_000, log: bool = True) -> tuple[np.ndarray, np.ndarray]:
    table = class_table()
    feats, sds = [], []
    t0 = time.perf_counter()
    for start in range(0, n, chunk):
        m = min(chunk, n - start)
        f, s = build_pool(pool_seed, start, m, table, COMB52, *TABLES)
        feats.append(f)
        sds.append(s)
        if log:
            done = start + m
            print(f"  {done:,} deals, {done / (time.perf_counter() - t0):,.0f}/s", flush=True)
    return np.concatenate(feats), np.concatenate(sds)


# --------------------------------------------------------------------------- features -> buckets

def features(feats: np.ndarray) -> dict[str, np.ndarray]:
    """Float features (exact: integer / denominator), arrays shaped like feats[..., 0]."""
    return {"cls": feats[..., 0].astype(np.int64),
            "fx": feats[..., 2] / FLOP_DEN[0], "fy": feats[..., 3] / FLOP_DEN[1],
            "tx": feats[..., 4] / TURN_DEN[0], "ty": feats[..., 5] / TURN_DEN[1],
            "hs": feats[..., 6] / RIVER_DEN, "blk": feats[..., 7].astype(np.int64)}


def _half_lattice(q: np.ndarray, den: int) -> list[float]:
    """Cuts moved to the middle between two attainable values (value = integer / den)."""
    return [(np.floor(x * den) + 0.5) / den for x in np.atleast_1d(q)]


def fit_cuts(feats: np.ndarray, grid: int = 10, river_bins: int = 25) -> dict:
    """Equal-mass cuts (section 5.5) from a sample of pool deals (both seats)."""
    f = {k: v.ravel() for k, v in features(feats).items()}
    qs = np.arange(1, grid) / grid
    out = {"grid": grid, "river_bins": river_bins}
    for st, (x, y, den) in {"flop": ("fx", "fy", FLOP_DEN), "turn": ("tx", "ty", TURN_DEN)}.items():
        xc = _half_lattice(np.quantile(f[x], qs), den[0])
        xb = np.searchsorted(xc, f[x], side="right")
        yc = []
        for b in range(grid):
            sel = f[y][xb == b]
            yc.append(_half_lattice(np.quantile(sel, qs), den[1]) if len(sel) else [1.0] * (grid - 1))
        out[st] = {"x": xc, "y": yc}
    out["river"] = _half_lattice(np.quantile(f["hs"], np.arange(1, river_bins) / river_bins), RIVER_DEN)
    return out


def bucket_ids(feats: np.ndarray, cuts: dict) -> np.ndarray:
    """(..., 4) bucket ids per street (preflop class, flop cell, turn cell, river bucket)."""
    f = features(feats)
    g = cuts["grid"]
    out = np.empty(feats.shape[:-1] + (4,), dtype=np.int32)
    out[..., 0] = f["cls"]
    for i, (st, x, y) in enumerate((("flop", "fx", "fy"), ("turn", "tx", "ty")), start=1):
        xc, yc = np.asarray(cuts[st]["x"]), np.asarray(cuts[st]["y"])
        xb = np.searchsorted(xc, f[x], side="right")
        yb = np.empty_like(xb)
        for b in range(g):
            sel = xb == b
            yb[sel] = np.searchsorted(yc[b], f[y][sel], side="right")
        out[..., i] = g * xb + yb
    out[..., 3] = 2 * np.searchsorted(np.asarray(cuts["river"]), f["hs"], side="right") + f["blk"]
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deals", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="data/cfr/pool_v1.npz")
    ap.add_argument("--fit", type=int, default=0, help="fit cuts on the first N deals of --pool")
    ap.add_argument("--pool", default=None)
    ap.add_argument("--cuts", default="lab/cfr/fast/cuts_v1.json")
    args = ap.parse_args(argv)
    if args.deals:
        feats, sd = make_pool(args.deals, args.seed)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        np.savez(args.out, feats=feats, sd=sd, seed=args.seed)
        print(f"pool: {len(sd):,} deals -> {args.out}")
    if args.fit:
        pool = np.load(args.pool or args.out)
        cuts = fit_cuts(pool["feats"][: args.fit])
        cuts.update({"version": "v1", "fit_deals": args.fit, "pool_seed": int(pool["seed"])})
        Path(args.cuts).write_text(json.dumps(cuts, indent=1) + "\n")
        print(f"cuts fitted on {args.fit:,} deals -> {args.cuts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
