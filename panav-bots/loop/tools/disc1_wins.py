"""Match-wins tables (match = one duplicate pair; win if chips>0, draw .5). disc1_wins.py RESULTS_DIR"""
import json, sys, math
from pathlib import Path
import numpy as np
d = Path(sys.argv[1])
TOUGH = ["opps_conv_opp3", "opps_new_eqrandom", "opps_new_exploiter", "opps_new_geometric", "opps_new_minraise", "spar_potctl", "lakshya1_200"]
def load(n, v):
    p = d / f"{n}_{v}.json"
    if not p.exists(): return None
    return {r["seed"]: r for r in json.loads(p.read_text())["pairs"]}
W = lambda r: 1.0 if r["chips"] > 0 else 0.5 if r["chips"] == 0 else 0.0
def row(n):
    B, C = load(n, "base"), load(n, "cand")
    if not B or not C: return None
    s = sorted(set(B) & set(C))
    wb = np.array([W(B[i]) for i in s]); wc = np.array([W(C[i]) for i in s])
    dc = np.array([C[i]["chips"] / C[i]["hands"] - B[i]["chips"] / B[i]["hands"] for i in s])
    dw = wc - wb
    return dict(n=n, N=len(s), wb=wb.sum(), wc=wc.sum(), dw=dw, dc=dc)
def show(title, names):
    rs = [r for r in map(row, names) if r]
    print(f"\n## {title}")
    print(f"{'bot':22s}{'N':>4s}{'base W':>8s}{'cand W':>8s}{'dWin pp':>9s}{'dChips c/h':>16s}")
    for r in rs:
        se = r["dw"].std(ddof=1) / math.sqrt(r["N"]) * 100; sc = r["dc"].std(ddof=1) / math.sqrt(r["N"])
        print(f"{r['n']:22s}{r['N']:4d}{r['wb']:8.1f}{r['wc']:8.1f}{r['dw'].mean()*100:+6.1f}+-{se:3.0f}{r['dc'].mean():+9.2f} +-{sc:4.2f}" + ("  <-- down >2SE" if r['dw'].mean()*100 < -2*se else ""))
    N = sum(r["N"] for r in rs); dw = np.concatenate([r["dw"] for r in rs]); dc = np.concatenate([r["dc"] for r in rs])
    wb = sum(r["wb"] for r in rs); wc = sum(r["wc"] for r in rs)
    print(f"POOLED N={N}: base {wb:.1f}/{N} = {100*wb/N:.1f}%  cand {wc:.1f}/{N} = {100*wc/N:.1f}%  dWin {dw.mean()*100:+.1f}pp +-{dw.std(ddof=1)/math.sqrt(N)*100:.1f} | chips {dc.mean():+.3f} +-{dc.std(ddof=1)/math.sqrt(N):.3f}")
allb = sorted(p.name[:-10] for p in d.glob("*_base.json") if "_500" not in p.name and p.name != "h2h.json" and not p.name.startswith("lakshya1_200"))
show("ALL 18 bots, Stage 1 (200h legs)", allb)
show("TOUGH group (D1's 7: conv_opp3 new_eqrandom new_exploiter new_geometric new_minraise potctl + lakshya1), Stage 1", TOUGH)
show("NON-TOUGH bots, Stage 1", [n for n in allb if n not in TOUGH])
show("Stage 2 (500h legs)", ["lakshya1_500", "new_eqrandom_500"])
p = d / "h2h.json"
if p.exists():
    rs = json.loads(p.read_text())["pairs"]; w = sum(W(r) for r in rs)
    print(f"\nHEAD-TO-HEAD cand vs base (200h): cand wins {w:.1f}/{len(rs)} = {100*w/len(rs):.0f}%")
