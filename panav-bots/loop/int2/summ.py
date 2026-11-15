"""INT2 summary: MATCH WINS first. usage: summ.py"""
import json, math
from pathlib import Path
R = Path("panav-bots/loop/results/int2")
def load(t):
    p = R / f"{t}.json"
    return json.loads(p.read_text()) if p.exists() else None
def res(d): return {r["seed"]: (1.0 if r["chips"] > 0 else .5 if r["chips"] == 0 else 0.0, r["chips"] / max(1, r["hands"])) for r in d["pairs"]}
def sd(x):
    n = len(x); m = sum(x) / n
    return math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1)) if n > 1 else float("nan")
OPP = "lakshya1 new_trapper conv_opp3 new_eqrandom eqtag potctl polar".split()
print("## h2h")
for t, lab in (("h2h_A_F", "A vs final"), ("h2h_A_C", "A vs probe-only")):
    d = load(t)
    if d:
        r = res(d); w = [v[0] for v in r.values()]; c = [v[1] for v in r.values()]
        print(f"{lab}: A MATCH WINS {sum(w):g}/{len(w)} ({100*sum(w)/len(w):.0f}%); chips/hand {sum(c)/len(c):+.2f} ± {sd(c)/math.sqrt(len(c)):.2f}")
def table(bots, suffix=""):
    print(f"| bot | " + " | ".join(f"{b} W/N" for b in bots) + " | chips/hand ± SE |\n|---|" + "---|" * (len(bots) + 1))
    tot = {}
    for b in bots:
        pass
    rows = []
    for o in OPP:
        cells = []; 
        for b in bots:
            d = load(f"{b}_{o}{suffix}")
            cells.append(d)
        rows.append((o, cells))
    return rows
def pooled(tag_prefix, suffix=""):
    W = N = 0; per = {}
    for o in OPP:
        d = load(f"{tag_prefix}_{o}{suffix}")
        if not d: continue
        for s, (w, c) in res(d).items(): per.setdefault(s, []).append(w)
    return per
print("\n## per-opponent 200h, 24 pairs (seeds 41000-41023)\n| opp | " + " | ".join(f"{b}" for b in "FABC") + " |\n|---|---|---|---|---|")
tot = {b: [0, 0, []] for b in "FABC"}
for o in OPP:
    cells = []
    for b in "FABC":
        d = load(f"{b}_{o}")
        if not d: cells.append("-"); continue
        r = res(d); w = sum(v[0] for v in r.values()); n = len(r); c = [v[1] for v in r.values()]
        cells.append(f"{w:g}/{n} ({sum(c)/n:+.2f}±{sd(c)/math.sqrt(n):.2f})")
        tot[b][0] += w; tot[b][1] += n; tot[b][2] += c
    print(f"| {o} | " + " | ".join(cells) + " |")
print("| **pooled** | " + " | ".join(f"{t[0]:g}/{t[1]} ({100*t[0]/t[1]:.1f}%) {sum(t[2])/len(t[2]):+.2f}" if t[1] else "-" for t in tot.values()) + " |")
# paired pooled A-F on common opponents
for x, y in (("A", "F"), ("A", "C"), ("A", "B"), ("C", "F"), ("B", "F")):
    dw = {}
    for o in OPP:
        a, b = load(f"{x}_{o}"), load(f"{y}_{o}")
        if a and b:
            ra, rb = res(a), res(b)
            for s in set(ra) & set(rb): dw.setdefault(s, []).append((ra[s][0] - rb[s][0], ra[s][1] - rb[s][1]))
    if dw:
        v = [sum(p[0] for p in l) / len(l) for l in dw.values()]; cc = [sum(p[1] for p in l) / len(l) for l in dw.values()]
        print(f"paired {x}-{y} over {len(dw)} seeds: dwin {100*sum(v)/len(v):+.1f} ± {100*sd(v)/math.sqrt(len(v)):.1f} pp; dchips/hand {sum(cc)/len(cc):+.3f} ± {sd(cc)/math.sqrt(len(cc)):.3f}")
print("\n## lakshya1 500h, 24 pairs")
for b in "AF":
    d = load(f"{b}_lakshya1_500")
    if d:
        r = res(d); w = sum(v[0] for v in r.values()); c = [v[1] for v in r.values()]
        print(f"{b}: {w:g}/{len(r)}; chips/hand {sum(c)/len(c):+.2f} ± {sd(c)/math.sqrt(len(c)):.2f}")
ff = sum(sum(p["ff_a"] for p in json.loads(f.read_text())["pairs"]) for f in R.glob("*.json") if "fuzz" not in f.name and "pairs" in f.read_text()[:3000])
print("forfeits (A side) total over all duels:", ff)
