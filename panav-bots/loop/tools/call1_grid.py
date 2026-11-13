"""call1: first-order counterfactual of potfold on logged rows (call1_rows.py): folding a call truncates the hand, so the
gain of folding is exact: -out per call (out = chips from the decision on; fold = 0). Opponent reaction not modelled."""
import json, math, sys
from collections import defaultdict

rows = []
for f in sys.argv[1:]:
    rows += json.load(open(f))
HANDS = {}
for r in rows:
    HANDS.setdefault(r["bot"], set())
FMIN, FMAX = 0.75, 1.2
el = [r for r in rows if r["act"] == "call" and FMIN <= r["f"] <= FMAX and not r["allin"]]
bots = sorted({r["bot"] for r in rows})


def stats(xs):
    n = len(xs)
    if n == 0:
        return 0, 0.0, 0.0
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    return n, m, sd / math.sqrt(n) if n else 0.0


print("calls of pot-size bets (not all-in): mean chips from the decision on (fold = 0)")
for cut in (0.8, 0.9, 0.95, 1.01):
    print(f"-- cut {cut}")
    for st in ("flop", "turn", "river"):
        for seat in (0, 1):
            xs = [r["out"] for r in el if r["street"] == st and r["seat"] == seat and r["px"] < cut]
            n, m, se = stats(xs); print(f"  {st:5s} seat{seat} n={n:5d} mean {m:+7.1f} ± {se:4.1f}")
print("by px bucket (all streets):")
for lo, hi in ((0, .35), (.35, .5), (.5, .65), (.65, .8), (.8, .9), (.9, .95), (.95, 1.01)):
    xs = [r["out"] for r in el if lo <= r["px"] < hi]; n, m, se = stats(xs); print(f"  px {lo:.2f}-{hi:.2f} n={n:5d} mean {m:+7.1f} ± {se:4.1f}")
print("per bot, cut .9: n, mean, sd")
bm = []
for b in bots:
    xs = [r["out"] for r in el if r["bot"] == b and r["px"] < 0.9]; n, m, se = stats(xs)
    sd = se * math.sqrt(max(n, 1)); print(f"  {b:14s} n={n:4d} mean {m:+7.1f} ± {se:4.1f} sd {sd:5.1f}")
    if n >= 20: bm.append(m)
if len(bm) > 1:
    mm = sum(bm) / len(bm); print("  between-bot SD of the mean:", math.sqrt(sum((x - mm) ** 2 for x in bm) / (len(bm) - 1)), "mean of means", mm)
xs = [r["out"] for r in el if r["px"] < 0.9]; n, m, se = stats(xs); print(f"pooled cut .9: n={n} mean {m:+.1f} sd {se*math.sqrt(n):.1f}")
print("kind: opening bet (raises==0) vs raise over our bet, px<.9")
for k, cond in (("open", lambda r: r["raises"] == 1), ("raise", lambda r: r["raises"] >= 2)):
    xs = [r["out"] for r in el if cond(r) and r["px"] < 0.9]; n, m, se = stats(xs); print(f"  {k} n={n} mean {m:+.1f} ± {se:.1f}")
