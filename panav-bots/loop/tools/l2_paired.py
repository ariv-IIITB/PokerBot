"""Paired delta between two file_duel --out JSONs (same seeds). usage: l2_paired.py base.json cand.json [hands_per_leg]"""
import json, sys, math
def load(p):
    j = json.load(open(p)); r = j["pairs"] if isinstance(j, dict) else j
    return {x["seed"]: x for x in r}
b = load(sys.argv[1])
c = load(sys.argv[2])
seeds = sorted(set(b) & set(c))
d = [(c[s]["chips"] / c[s]["hands"]) - (b[s]["chips"] / b[s]["hands"]) for s in seeds]
n = len(d); m = sum(d) / n; sd = (sum((x - m) ** 2 for x in d) / max(n - 1, 1)) ** .5
print(f"n={n} base {sum(b[s]['chips']/b[s]['hands'] for s in seeds)/n:+.3f} cand {sum(c[s]['chips']/c[s]['hands'] for s in seeds)/n:+.3f} paired delta {m:+.3f} +- {sd/math.sqrt(n):.3f} (chips/hand)")
