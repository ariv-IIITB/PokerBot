"""Report for overfit.jsonl: per opponent, each bot's 2-leg score and chips/hand, and the paired
final - v3 difference on the seeds both have played (chips/hand, with SE)."""
import json
import math
import sys
from collections import defaultdict

rows = [json.loads(l) for l in open(sys.argv[1])]
errs = [r for r in rows if "error" in r]
rows = [r for r in rows if "error" not in r]
by = defaultdict(dict)                     # (opp) -> bot -> seed -> row
for r in rows:
    by[r["opp"]].setdefault(r["bot"], {})[r["seed"]] = r


def score(r):
    if r["forfeits"][0] or r["forfeits"][1]:
        return 1.0 if r["forfeits"][1] > r["forfeits"][0] else 0.0
    t = sum(r["chips"])
    return 1.0 if t > 0 else (0.0 if t < 0 else 0.5)


def mean_se(xs):
    n = len(xs)
    if n < 2:
        return (xs[0] if xs else float("nan")), float("nan")
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(v / n)


print(f"{'opponent':18s} {'bot':9s} {'n':>4s} {'W-L':>8s} {'score':>13s} {'chips/hand':>16s} ff err")
pool_diff = []
for opp in sorted(by):
    for bot in ("d_xfinal", "d_xv3"):
        d = by[opp].get(bot, {})
        if not d:
            continue
        s = [score(r) for r in d.values()]
        c = [sum(r["chips"]) / r["hands"] for r in d.values()]
        sm, sse = mean_se(s)
        cm, cse = mean_se(c)
        w = sum(1 for x in s if x == 1.0)
        ff = sum(1 for r in d.values() if r["forfeits"][0] or r["forfeits"][1])
        er = sum(r["errors"][0] for r in d.values())
        print(f"{opp:18s} {bot[2:]:9s} {len(s):4d} {w:>3d}-{len(s) - w:<4d} {sm:.3f} +- {sse:.3f} "
              f"{cm:+7.3f} +- {cse:.3f} {ff:2d} {er:3d}")
    f, v = by[opp].get("d_xfinal", {}), by[opp].get("d_xv3", {})
    common = sorted(set(f) & set(v))
    if len(common) >= 2:
        diff = [sum(f[k]["chips"]) / f[k]["hands"] - sum(v[k]["chips"]) / v[k]["hands"] for k in common]
        sd = [score(f[k]) - score(v[k]) for k in common]
        dm, dse = mean_se(diff)
        smm, sse = mean_se(sd)
        pool_diff.append((opp, len(common), dm, dse))
        print(f"{'':18s} final-v3  {len(common):4d} paired: score {smm:+.3f} +- {sse:.3f}, "
              f"chips/hand {dm:+.3f} +- {dse:.3f}  ({dm / dse if dse > 0 else 0:+.1f} SE)")
if pool_diff:
    # pooled over opponents: mean of per-opponent differences, SE from their SEs
    m = sum(d for _, _, d, _ in pool_diff) / len(pool_diff)
    se = math.sqrt(sum(s * s for _, _, _, s in pool_diff)) / len(pool_diff)
    print(f"\npooled final - v3 over {len(pool_diff)} opponents (equal weight): chips/hand {m:+.3f} +- {se:.3f}"
          f"  ({m / se if se > 0 else 0:+.1f} SE)")
if errs:
    print(f"\n{len(errs)} runner errors, e.g. {errs[0]}")
