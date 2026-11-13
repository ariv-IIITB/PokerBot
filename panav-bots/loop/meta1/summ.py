import sys, math, json
sys.path.insert(0, "panav-bots/loop/meta1")
from effects import table, SW
T = table(); EX = {"s1_ranges"}
bots = [b for b in T if b not in EX]
FOLDS = {"F1": "eqtag polar new_lag conv_opp3 lakshya1 s5_preflop".split(), "F2": "trapper potctl s6_discard new_trapper conv_opp4 new_minraise s2_rollout".split(),
         "F3": "betfold light3b tilt s3_exploit s7_solver s9_sizing new_rules new_geometric".split(), "F4": "donk adapt discardread s4_balanced s8_meta s10_regret new_exploiter new_eqrandom".split()}
for s in SW:
    print(s)
    for f, bs in FOLDS.items():
        d = [100 * T[b][s]["dwin"] for b in bs if b in T and s in T[b]]; c = [T[b][s]["dchips"] for b in bs if b in T and s in T[b]]
        print(f"  {f}: dwin {sum(d)/len(d):+5.1f}pp  dchips {sum(c)/len(c):+.2f}  (n={len(d)})")
    # even/odd seed halves
    for h, sl in (("even", slice(0, None, 2)), ("odd", slice(1, None, 2))):
        d = [100 * sum(T[b][s]["dw_list"][sl]) / len(T[b][s]["dw_list"][sl]) for b in bots]
        print(f"  seeds {h}: dwin {sum(d)/len(d):+5.1f}pp")
    # pooled W/N
    wb = sum(T[b]["base"]["win"] * 24 for b in bots); wc = sum(T[b][s]["cand_win"] * 24 for b in bots); n = 24 * len(bots)
    print(f"  pooled match wins base {wb:.1f}/{n} = {100*wb/n:.1f}%  cand {wc:.1f}/{n} = {100*wc/n:.1f}%")
