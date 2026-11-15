"""Pass-rule aggregation for DISC1.  disc1_agg.py RESULTS_DIR
Per bot: paired delta (cand - base) in chips/hand by seed; pooled over all 200h bots; match wins (pair chips > 0 -> 1, = 0 -> .5)."""
import json, sys, math
from pathlib import Path
import numpy as np

d = Path(sys.argv[1])

def load(p):
    j = json.loads(Path(p).read_text())
    return {r["seed"]: r for r in j["pairs"]}

def cph(r): return r["chips"] / r["hands"]
def win(r): return 1.0 if r["chips"] > 0 else 0.5 if r["chips"] == 0 else 0.0
def se(v): return float(np.std(v, ddof=1) / math.sqrt(len(v))) if len(v) > 1 else float("nan")

def per_bot(name):
    b, c = d / f"{name}_base.json", d / f"{name}_cand.json"
    if not (b.exists() and c.exists()): return None
    B, C = load(b), load(c); seeds = sorted(set(B) & set(C))
    return dict(name=name, seeds=seeds,
                delta=[cph(C[s]) - cph(B[s]) for s in seeds], base=[cph(B[s]) for s in seeds], cand=[cph(C[s]) for s in seeds],
                wb=[win(B[s]) for s in seeds], wc=[win(C[s]) for s in seeds],
                ff=sum(B[s]["ff_a"] + C[s]["ff_a"] for s in seeds))

names = sorted(p.name[:-10] for p in d.glob("*_base.json") if not p.name.startswith(("lakshya1_500", "new_eqrandom_500")) and "_500" not in p.name)
res = [r for r in (per_bot(n) for n in names) if r]
print(f"{'bot':22s}{'pairs':>6s}{'base c/h':>10s}{'cand c/h':>10s}{'delta c/h':>16s}{'wins b/c':>12s}")
alld, allwb, allwc, flag = [], [], [], []
for r in res:
    dl = np.array(r["delta"]); s = se(dl)
    print(f"{r['name']:22s}{len(dl):6d}{np.mean(r['base']):+10.2f}{np.mean(r['cand']):+10.2f}{dl.mean():+9.2f} +-{s:4.2f}{np.mean(r['wb']):7.2f}/{np.mean(r['wc']):.2f}  ff={r['ff']}")
    alld += list(dl); allwb += r["wb"]; allwc += r["wc"]
    if dl.mean() < -2 * s: flag.append(r["name"])
if alld:
    a = np.array(alld); s = se(a)
    print(f"\nPOOLED ({len(res)} bots, {len(a)} pairs): delta {a.mean():+.3f} +-{s:.3f} chips/hand  (ratio {a.mean() / s:.2f})")
    print(f"match wins pooled: base {np.mean(allwb):.3f} cand {np.mean(allwc):.3f}   (cand-base {np.mean(allwc) - np.mean(allwb):+.3f})")
    print("bots down by > 2 SE:", flag or "none")
    print("PASS pooled>=+0.10 and >=1.5 SE:", a.mean() >= 0.10 and a.mean() >= 1.5 * s, "| wins not lower:", np.mean(allwc) >= np.mean(allwb))
for f in ("h2h",):
    p = d / "h2h.json"
    if p.exists():
        j = json.loads(p.read_text()); v = [cph(r) for r in j["pairs"]]
        print(f"\nhead-to-head cand vs base: {np.mean(v):+.3f} +-{se(v):.3f} chips/hand over {len(v)} pairs; cand match wins {np.mean([win(r) for r in j['pairs']]):.3f}")
for n in ("lakshya1_500", "new_eqrandom_500"):
    r = per_bot(n)
    if r:
        dl = np.array(r["delta"])
        print(f"{n} (500h legs): {len(dl)} pairs base {np.mean(r['base']):+.2f} cand {np.mean(r['cand']):+.2f} delta {dl.mean():+.2f} +-{se(dl):.2f}  wins {np.mean(r['wb']):.2f}/{np.mean(r['wc']):.2f}")
