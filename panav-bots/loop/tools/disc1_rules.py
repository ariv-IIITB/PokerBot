"""Re-score keep rules offline on disc1_eval rows (cross-fitted loss vs the best keep, equity points, +-SE).
  disc1_rules.py rows.json [...]"""
import json, sys
import numpy as np

rows = []
for f in sys.argv[1:]:
    rows += json.load(open(f))

def loss(x, k, m="opt"):
    A = np.array(x["eqA_" + m]); B = np.array(x["eqB_" + m])
    return 0.5 * ((B[A.argmax()] - B[k]) + (A[B.argmax()] - A[k]))

def stat(v):
    v = np.array(v) * 100
    return f"{v.mean():5.2f} +-{v.std(ddof=1) / np.sqrt(len(v)):4.2f}"

slot0 = lambda x: x["slot"].index(0)
def blend(delta):
    def f(x):
        s = x["s1"]; c = x["chosen"]
        return c if s[c] >= max(s) - delta else slot0(x)
    return f
rules = {"blueprint": lambda x: x["chosen"], "slot0(max S1)": slot0}
for d in (0.01, 0.02, 0.04, 0.08):
    rules[f"bp if S1>=max-{d}"] = blend(d)
print(f"n={len(rows)}")
for n, f in rules.items():
    print(f"{n:22s} opt {stat([loss(x, f(x)) for x in rows])} | rnd {stat([loss(x, f(x), 'rnd') for x in rows])}")
