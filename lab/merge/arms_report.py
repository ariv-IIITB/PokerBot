"""Report for arms_run output: per opponent, each bot's two-leg score and chips/hand, and the paired
difference of each arm vs the baseline (default d_xfinal) on the seeds both played.

    python arms_report.py OUT.jsonl [BASELINE]"""
import json
import math
import sys
from collections import defaultdict

rows = [json.loads(l) for l in open(sys.argv[1])]
base = sys.argv[2] if len(sys.argv) > 2 else "d_xfinal"
errs = [r for r in rows if "error" in r]
rows = [r for r in rows if "error" not in r]
by = defaultdict(lambda: defaultdict(dict))
for r in rows:
    by[r["opp"]][r["bot"]][r["seed"]] = r
bots = sorted({r["bot"] for r in rows}, key=lambda b: (b != base, b))


def score(r):
    if r["forfeits"][0] or r["forfeits"][1]:
        return 1.0 if r["forfeits"][1] > r["forfeits"][0] else 0.0
    t = sum(r["chips"])
    return 1.0 if t > 0 else (0.0 if t < 0 else 0.5)


def cph(r):
    return sum(r["chips"]) / r["hands"]


def mean_se(xs):
    n = len(xs)
    if n < 2:
        return (xs[0] if xs else float("nan")), float("nan")
    m = sum(xs) / n
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n)


pooled = defaultdict(list)
for opp in sorted(by):
    print(f"== {opp}")
    for b in bots:
        d = by[opp].get(b)
        if not d:
            continue
        sm, sse = mean_se([score(r) for r in d.values()])
        cm, cse = mean_se([cph(r) for r in d.values()])
        ff = sum(1 for r in d.values() if r["forfeits"][0] or r["forfeits"][1])
        line = f"  {b:14s} n={len(d):3d} score {sm:.3f} +- {sse:.3f}  chips/hand {cm:+.3f} +- {cse:.3f}"
        line += f"  ff {ff}" if ff else ""
        if b != base and base in by[opp]:
            common = sorted(set(d) & set(by[opp][base]))
            if len(common) >= 2:
                dm, dse = mean_se([cph(d[k]) - cph(by[opp][base][k]) for k in common])
                ds, dsse = mean_se([score(d[k]) - score(by[opp][base][k]) for k in common])
                pooled[b].append((dm, dse))
                line += (f"   vs {base[2:]}: chips {dm:+.3f} +- {dse:.3f} ({dm / dse if dse > 0 else 0:+.1f} SE),"
                         f" score {ds:+.3f} +- {dsse:.3f}")
        print(line)
print()
for b, xs in pooled.items():
    m = sum(d for d, _ in xs) / len(xs)
    se = math.sqrt(sum(s * s for _, s in xs)) / len(xs)
    print(f"pooled {b} - {base} over {len(xs)} opponents (equal weight): chips/hand {m:+.3f} +- {se:.3f}"
          f" ({m / se if se > 0 else 0:+.1f} SE)")
if errs:
    print(f"\n{len(errs)} runner errors, e.g. {errs[0]}")
