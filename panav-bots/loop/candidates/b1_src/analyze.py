import json, math, glob, os, sys
R="/home/user/pokerbot/panav-bots/loop/results"
dev=["eqtag","trapper","s1_ranges","s2_rollout","s3_exploit"]
hold=["potctl","polar","s4_balanced","s5_preflop","s6_discard","betfold","light3b","s7_solver","s8_meta","s9_sizing","donk","adapt","tilt","discardread","s10_regret"]
old=["old_"+x for x in "conv_opp3 conv_opp4 new_eqrandom new_exploiter new_geometric new_lag new_minraise new_rules new_trapper".split()]
def per(f): 
    d=json.load(open(f)); return {p["seed"]:p["chips"]/max(1,p["hands"]) for p in d["pairs"]}, d
def delta(b):
    fb,fc=f"{R}/base_{b}.json",f"{R}/cand_b1_{b}.json"
    if not (os.path.exists(fb) and os.path.exists(fc)): return None
    pb,db=per(fb); pc,dc=per(fc)
    s=sorted(set(pb)&set(pc)); x=[pc[i]-pb[i] for i in s]; n=len(x); m=sum(x)/n
    se=math.sqrt(sum((v-m)**2 for v in x)/(n-1)/n)
    ff=sum(p["ff_a"] for p in dc["pairs"])
    return m,se,n,sum(pb[i] for i in s)/n,sum(pc[i] for i in s)/n,ff
def pooled(names):
    rows=[(b,delta(b)) for b in names]; rows=[(b,r) for b,r in rows if r]
    if not rows: return None
    m=sum(r[0] for _,r in rows)/len(rows); se=math.sqrt(sum(r[1]**2 for _,r in rows))/len(rows)
    return m,se,len(rows)
for name,g in (("DEV",dev),("HOLDOUT B2-B4",hold),("OLD POOL",old),("REGRESSION",["lakshya1"])):
    print("##",name)
    for b in g:
        r=delta(b)
        if r: print(f"| {b} | {r[3]:+.2f} | {r[4]:+.2f} | {r[0]:+.2f} ± {r[1]:.2f} | {r[2]} | {'ZSCORE %.1f'%(r[0]/r[1]) if r[1]>0 else ''} | ff {r[5]} |")
    p=pooled(g)
    if p: print(f"POOLED mean delta {p[0]:+.3f} ± {p[1]:.3f} (bots {p[2]})")
