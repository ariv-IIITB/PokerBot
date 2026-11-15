"""OPUS2 aggregation: per-bot and pooled MATCH WINS (A vs lock, post-hoc exact), capped chips, adjacent-order
sensitivity, and the real confirmation arm (L_*.json vs A_*.json, paired by seed)."""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lockpost import analyse, score
R = Path(sys.argv[1] if len(sys.argv) > 1 else "panav-bots/loop/results/opus2/val")
C = 1000
def se(xs):
    n = len(xs); m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n) if n > 1 else float("nan")
def clip(x): return max(-C, min(C, x))
rows_all, out = [], []
out.append("| bot | n | A wins | lock wins (post-hoc) | d wins pp ± SE | fired | A chips/h | A capped/h | adjacent-order d pp |")
out.append("|---|---|---|---|---|---|---|---|---|")
for f in sorted(R.glob("A_*.json")):
    d = json.load(open(f)); T = d["hands"]; P = d["pairs"]
    rows = analyse(P, T)
    adj = []
    for p in P:
        h = len(p["deltas"]) // 2
        q = dict(p); q["deltas"] = [x for k in range(h) for x in (p["deltas"][k], p["deltas"][h + k])]
        adj.append(q)
    ra = analyse(adj, T)
    n = len(rows); dw = [r["sc"] - r["sa"] for r in rows]; da = [r["sc"] - r["sa"] for r in ra]
    wa = sum(r["sa"] for r in rows); wc = sum(r["sc"] for r in rows)
    ch = [p["chips"] / T for p in P]; cc = [clip(p["chips"]) / T for p in P]
    rows_all.append((f.stem[2:], rows, dw, da, ch, cc))
    out.append(f"| {f.stem[2:]} | {n} | {wa:g} ({100*wa/n:.0f}%) | {wc:g} ({100*wc/n:.0f}%) | {100*sum(dw)/n:+.1f} ± {100*se(dw):.1f} | "
               f"{sum(r['fired'] for r in rows)} | {sum(ch)/n:+.2f} ± {se(ch):.2f} | {sum(cc)/n:+.2f} | {100*sum(da)/n:+.1f} |")
if rows_all:
    per_bot = [100 * sum(x[2]) / len(x[2]) for x in rows_all]
    allw = [v for x in rows_all for v in x[2]]; alla = [v for x in rows_all for v in x[3]]
    wa = sum(r["sa"] for x in rows_all for r in x[1]); wc = sum(r["sc"] for x in rows_all for r in x[1]); N = len(allw)
    out.append(f"\nPOOLED {len(rows_all)} bots, {N} matches: A {wa:g}/{N} ({100*wa/N:.1f}%) -> lock {wc:g}/{N} ({100*wc/N:.1f}%): "
               f"{100*sum(allw)/N:+.2f} ± {100*se(allw):.2f} pp (mean of per-bot {sum(per_bot)/len(per_bot):+.2f} ± {se(per_bot):.2f}); "
               f"adjacent order {100*sum(alla)/N:+.2f} ± {100*se(alla):.2f} pp")
# real confirmation arm
conf = []
for f in sorted(R.glob("L_*.json")):
    b = f.stem[2:]; fa = R / f"A_{b}.json"
    if not fa.exists(): continue
    L = {p["seed"]: p for p in json.load(open(f))["pairs"]}; A = {p["seed"]: p for p in json.load(open(fa))["pairs"]}
    T = json.load(open(f))["hands"]; s = sorted(set(L) & set(A))
    dw = [score(L[k]["chips"]) - score(A[k]["chips"]) for k in s]
    dc = [(L[k]["chips"] - A[k]["chips"]) / T for k in s]; dcc = [(clip(L[k]["chips"]) - clip(A[k]["chips"])) / T for k in s]
    wl = sum(score(L[k]["chips"]) for k in s); wa = sum(score(A[k]["chips"]) for k in s)
    ff = sum(L[k]["ff_a"] for k in s)
    conf.append((b, s, dw, dc, dcc))
    out.append(f"REAL {b}: n {len(s)} wins A {wa:g} -> L {wl:g} ({100*sum(dw)/len(s):+.1f} ± {100*se(dw):.1f} pp); "
               f"chips/h {sum(dc)/len(s):+.3f} ± {se(dc):.3f}; capped/h {sum(dcc)/len(s):+.3f} ± {se(dcc):.3f}; L forfeits {ff}; "
               f"L min bank left {min(L[k]['bank_left_a'] for k in s):.1f}s worst {max(L[k]['worst_a'] for k in s):.2f}s")
if conf:
    dw = [v for c in conf for v in c[2]]; dc = [v for c in conf for v in c[3]]; dcc = [v for c in conf for v in c[4]]
    out.append(f"REAL POOLED {len(conf)} bots {len(dw)} matches: wins {100*sum(dw)/len(dw):+.2f} ± {100*se(dw):.2f} pp; chips/h "
               f"{sum(dc)/len(dc):+.3f} ± {se(dc):.3f}; capped/h {sum(dcc)/len(dcc):+.3f} ± {se(dcc):.3f}")
h = R / "h2h_L_A.json"
if h.exists():
    P = json.load(open(h))["pairs"]; w = sum(score(p["chips"]) for p in P); ch = [p["chips"] / 1000 for p in P]
    out.append(f"H2H lock vs A: MATCH WINS {w:g}/{len(P)} ({100*w/len(P):.1f}%), chips/h {sum(ch)/len(ch):+.3f} ± {se(ch):.3f}, "
               f"forfeits {sum(p['ff_a'] for p in P)}/{sum(p['ff_b'] for p in P)}")
print("\n".join(out))
