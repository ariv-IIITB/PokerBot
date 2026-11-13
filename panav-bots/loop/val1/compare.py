"""compare.py DIR BASE_TAG CAND_TAG  -> per-bot paired delta (cand - base, chips/hand, paired by seed), pooled, scores."""
import json, math, sys, glob, os
d, tb, tc = sys.argv[1:4]
def load(tag):
    out = {}
    for f in sorted(glob.glob(f"{d}/{tag}/*.json")):
        j = json.load(open(f)); out[os.path.basename(f)[:-5]] = {p["seed"]: (p["chips"] / max(1, p["hands"]), p["score"]) for p in j["pairs"]}
    return out
B, C = load(tb), load(tc)
allx, sb, sc = [], 0.0, 0.0
print(f"{'bot':14s} {'base':>7s} {'cand':>7s} {'delta':>14s} {'z':>5s} {'score b/c':>10s}  n")
worst = []
for bot in B:
    if bot not in C: continue
    seeds = sorted(set(B[bot]) & set(C[bot]))
    xs = [C[bot][s][0] - B[bot][s][0] for s in seeds]
    n = len(xs); m = sum(xs) / n
    se = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n) if n > 1 else float("nan")
    b = sum(B[bot][s][0] for s in seeds) / n; c = sum(C[bot][s][0] for s in seeds) / n
    sbb = sum(B[bot][s][1] for s in seeds); scc = sum(C[bot][s][1] for s in seeds)
    print(f"{bot:14s} {b:+7.2f} {c:+7.2f} {m:+6.2f} ±{se:5.2f} {m / se if se else 0:+5.1f} {sbb:4.1f}/{scc:4.1f}  {n}")
    allx += xs; sb += sbb; sc += scc; worst.append((m / se if se else 0, bot))
n = len(allx)
if n > 1:
    m = sum(allx) / n; se = math.sqrt(sum((x - m) ** 2 for x in allx) / (n - 1) / n)
    print(f"POOLED delta {m:+.3f} ± {se:.3f} (z {m / se:+.1f}, pairs {n}); match score sum base {sb:.1f} cand {sc:.1f}; min bot z {min(worst)[0]:+.1f} ({min(worst)[1]})")
