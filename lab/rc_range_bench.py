"""RC: cost of the river solver's pieces at FULL ranges (their range, our own range, ranks, solve) on recorded spots.

    .venv/bin/python -m lab.rc_range_bench --spots 40 --spots-file logs/rc/spots40.pkl --box-ms 10,20,40
"""
from __future__ import annotations

import argparse
import os
import pickle
import time

import numpy as np

from bot.strategy.own_range import own_range_weights
from bot.strategy.river_solver import INF, TreeCfg, hand_ranks, solve_river
from lab.river_bench import record_spots


def pieces(c):
    rec = c.rec
    ev = rec.state.rules.evaluator
    t0 = time.perf_counter()
    pool = np.array(sorted(rec.pool), dtype=np.int64)
    i, j = np.triu_indices(len(pool), 1)
    opp = np.stack([pool[i], pool[j]], axis=1)
    hole = sorted(int(x) for x in c.hole)
    seen = set(int(x) for x in rec.mapping.values()) - set(hole)
    mine = np.array([x for x in range(52) if x not in seen], dtype=np.int64)
    i, j = np.triu_indices(len(mine), 1)
    hero = np.stack([mine[i], mine[j]], axis=1)
    idx = int(np.nonzero((hero[:, 0] == hole[0]) & (hero[:, 1] == hole[1]))[0][0])
    t1 = time.perf_counter()
    w_opp = c.opponent.range_weights(rec, opp, c.rng)
    t2 = time.perf_counter()
    w_hero = own_range_weights(rec, hero, c.rng)
    t3 = time.perf_counter()
    board = np.array(c.board, dtype=np.intp)
    rh, ro = hand_ranks(ev, hero, board), hand_ranks(ev, opp, board)
    t4 = time.perf_counter()
    return (hero, w_hero, rh, opp, w_opp, ro, idx), dict(combos=t1 - t0, theirs=t2 - t1, ours=t3 - t2, ranks=t4 - t3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spots", type=int, default=40)
    ap.add_argument("--spots-file", default="")
    ap.add_argument("--box-ms", default="10,20,40")
    ap.add_argument("--first-seed", type=int, default=30000)
    a = ap.parse_args()
    if a.spots_file and os.path.exists(a.spots_file):
        spots = pickle.load(open(a.spots_file, "rb"))[:a.spots]
    else:
        spots = record_spots(a.spots, first_seed=a.first_seed)
        if a.spots_file:
            pickle.dump(spots, open(a.spots_file, "wb"))
    cfg = TreeCfg(bet_sizes=(1.0, INF), raise_sizes=(1.0, INF))
    warm = pieces(spots[0])
    for box in [float(x) / 1e3 for x in a.box_ms.split(",")]:
        T = {k: [] for k in ("combos", "theirs", "ours", "ranks")}
        its, tot = [], []
        for c in spots:
            t0 = time.perf_counter()
            (hero, wh, rh, opp, wo, ro, idx), tm = pieces(c)
            wo = np.maximum(wo, 1e-9 * wo.max()); wh = np.maximum(wh, 1e-9 * wh.max())
            from bot.strategy.river_solver import RiverSpot
            r = solve_river(c.spot, hero, wh, rh, opp, wo, ro, idx, t0 + box, cfg=cfg, auto=True)
            tot.append(time.perf_counter() - t0)
            its.append(r.iterations if r else 0)
            for k in T:
                T[k].append(tm[k])
        ms = lambda v: f"{np.median(v) * 1e3:.2f} (p90 {np.percentile(v, 90) * 1e3:.2f})"
        print(f"box {box * 1e3:.0f} ms: " + ", ".join(f"{k} {ms(v)}" for k, v in T.items())
              + f"; passes median {int(np.median(its))}, <20: {sum(i < 20 for i in its)}/{len(its)}; total {ms(tot)} ms")


if __name__ == "__main__":
    main()
