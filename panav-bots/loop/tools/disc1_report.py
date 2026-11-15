"""Aggregate disc1_eval rows: mean loss (equity points) +- SE by model, type, seat. Usage: disc1_report.py rows.json [...]"""
import json, sys, collections
import numpy as np

rows = []
for f in sys.argv[1:]:
    rows += json.load(open(f))

def ms(v):
    v = np.array(v, float) * 100
    return f"{v.mean():5.2f} +-{v.std(ddof=1) / np.sqrt(len(v)):4.2f} (n={len(v)})" if len(v) > 1 else "n/a"

print("== overall (equity points, loss of chosen keep vs best keep, cross-fitted)")
for k in ("loss_rnd", "loss_opt", "loss_act"):
    print(f"  {k}: {ms([r[k] for r in rows if k in r])}")
print("  share >=3pts (opt):", np.mean([r["loss_opt"] >= .03 for r in rows]).round(3))
print("== by bot (opt)")
for b in sorted({r['bot'] for r in rows}):
    print(f"  {b:14s} rnd {ms([r['loss_rnd'] for r in rows if r['bot']==b])} | opt {ms([r['loss_opt'] for r in rows if r['bot']==b])}")
print("== by seat (opt)")
for s in ("button", "big_blind"):
    print(f"  {s:10s} {ms([r['loss_opt'] for r in rows if r['seat']==s])}")
print("== by chosen type (opt): mean loss, share>=3pts")
by = collections.defaultdict(list)
for r in rows: by[r["type"]].append(r)
for t, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
    print(f"  {t:20s} {ms([r['loss_opt'] for r in rs])}  >=3: {np.mean([r['loss_opt']>=.03 for r in rs]):.3f}  rnd {ms([r['loss_rnd'] for r in rs])}")
print("== mistakes >=3pts (opt): chosen type -> best type")
c = collections.Counter((r["type"], r["type_best"]) for r in rows if r["loss_opt"] >= .03)
for (a, b), n in c.most_common(8): print(f"  {a:18s}-> {b:18s} {n}")
print("== by pot at discard (opt)")
for lo, hi in ((0, 10), (10, 20), (20, 40), (40, 80), (80, 500)):
    v = [r["loss_opt"] for r in rows if lo <= r["pot"] < hi]
    if len(v) > 5: print(f"  pot {lo}-{hi}: {ms(v)}")
print("== by flop aggression (opt)")
for nm, f in (("nobody bet", lambda r: r["flop_me_bet"] + r["flop_opp_bet"] == 0), ("we bet only", lambda r: r["flop_me_bet"] > 0 and r["flop_opp_bet"] == 0),
              ("opp bet only", lambda r: r["flop_me_bet"] == 0 and r["flop_opp_bet"] > 0), ("both", lambda r: r["flop_me_bet"] > 0 and r["flop_opp_bet"] > 0)):
    v = [r["loss_opt"] for r in rows if f(r)]
    if len(v) > 5: print(f"  {nm:12s} {ms(v)}")
