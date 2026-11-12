"""Paired delta between two file_duel sum.json (same seeds): per-seed chips/hand diff, mean +- SE.  nb1_cmp.py BASE.json CAND.json"""
import json, sys, math
def load(p):
    d = json.load(open(p)); return {r["seed"]: r["chips"] / r["hands"] for r in d["pairs"]}, d
a, da = load(sys.argv[1]); b, db = load(sys.argv[2])
ks = sorted(set(a) & set(b)); x = [b[k] - a[k] for k in ks]; n = len(x)
m = sum(x) / n; sd = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1)); se = sd / math.sqrt(n)
print(f"paired delta (cand-base) {m:+.3f} +- {se:.3f} chips/hand over {n} seeds; base {da['mean']:+.3f} cand {db['mean']:+.3f}; score {da['score']:.3f}->{db['score']:.3f}")
