"""Paired deltas cand-base per bot from results/v1/{base,cand}_<bot>.json (per-seed chips/hands)."""
import json, math, sys, glob, os
D = "panav-bots/loop/results/v1"
def per(f):
    return {p["seed"]: p["chips"] / max(1, p["hands"]) for p in json.load(open(f))["pairs"]}
def ms(x):
    n = len(x); m = sum(x) / n
    return m, (math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1) / n) if n > 1 else float("nan"))
rows = []
for bf in sorted(glob.glob(D + "/base_*.json")):
    n = os.path.basename(bf)[5:-5]; cf = f"{D}/cand_{n}.json"
    if not os.path.exists(cf): continue
    b, c = per(bf), per(cf); s = sorted(set(b) & set(c))
    d = [c[k] - b[k] for k in s]; dm, dse = ms(d)
    rows.append((n, ms([b[k] for k in s]), ms([c[k] for k in s]), dm, dse, len(s)))
    ca, ba = json.load(open(cf)), json.load(open(bf))
for n, b, c, dm, dse, k in rows:
    print(f"{n:16s} base {b[0]:+6.2f}±{b[1]:.2f}  cand {c[0]:+6.2f}±{c[1]:.2f}  delta {dm:+6.2f}±{dse:.2f}  z={dm/dse if dse else 0:+.1f} n={k}")
oth = [r for r in rows if r[0] != "lakshya"]
if oth:
    # pooled per-pair: mean over bots of per-seed delta -> SE across bots' independent seeds: sqrt(sum se^2)/k
    k = len(oth); pm = sum(r[3] for r in oth) / k; pse = math.sqrt(sum(r[4] ** 2 for r in oth)) / k
    print(f"POOLED non-lakshya (mean of {k} bot deltas): {pm:+.3f} ± {pse:.3f}")
