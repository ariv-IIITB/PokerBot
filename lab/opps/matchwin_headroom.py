"""MW headroom: how often is a match still open late, and the best a free variance scale could add.
Usage: python -m lab.opps.matchwin_headroom DIR_OF_RECORDINGS (e.g. logs/records/s0_9000 from tier4/s0); never reads d_new_rules."""
import gzip, json, glob, os, math, sys
import numpy as np
D = sys.argv[1]
ks = (200, 300, 350)
tot = {k: [0,0,0] for k in ks}   # n, open(|z|<1), flipped
print(f"{'bot':16} n  sd/h  " + "  ".join(f"k={k}: open|z<1  flip" for k in ks))
for f in sorted(glob.glob(D + "/*.json.gz")):
    b = os.path.basename(f)[:-8]
    if b == "d_new_rules": continue
    d = json.load(gzip.open(f))
    rows = {k: [0,0,0] for k in ks}; sds = []
    for p in d["pairs"]:
        for m in p["matches"]:
            dl = np.array([h["delta"] for h in m["hands"]], float)
            N = len(dl); c = np.cumsum(dl); fin = c[-1]
            sd = dl.std(); sds.append(sd)
            for k in ks:
                lead = c[k-1]; z = lead / (sd * math.sqrt(N - k))
                r = rows[k]; r[0] += 1; r[1] += abs(z) < 1; r[2] += (lead > 0) != (fin > 0)
    print(f"{b:16} {rows[200][0]:3d} {np.mean(sds):5.0f}  " + "  ".join(f"{rows[k][1]/rows[k][0]:6.2f} {rows[k][2]/rows[k][0]:6.2f}      " for k in ks))
    for k in ks:
        for i in range(3): tot[k][i] += rows[k][i]
print("ALL (no d_new_rules)  " + "  ".join(f"k={k}: open {tot[k][1]/tot[k][0]:.2f} flip {tot[k][2]/tot[k][0]:.2f}" for k in ks))

# ---- upper bound: scale post-hand-k deviations by s(z) (ahead <1, behind >1), strong bots only
import numpy as np

STRONG = ["d_conv_opp3","d_new_exploiter","d_new_lag","d_new_minraise","d_new_trapper"]
def run(k, s_ahead, s_behind, mean_free=True):
    base=[];new=[]
    for b in STRONG:
        d = json.load(gzip.open(f"{D}/{b}.json.gz"))
        for p in d["pairs"]:
            for m in p["matches"]:
                dl = np.array([h["delta"] for h in m["hands"]], float); N=len(dl)
                mu = dl.mean(); L = dl[:k].sum(); rem = dl[k:]
                sd = dl.std(); z = L/(sd*math.sqrt(N-k))
                # smooth scale: ahead -> s_ahead, behind -> s_behind, weight by |z| up to 1
                w = min(abs(z),1.0)
                s = 1 + w*((s_ahead if L>0 else s_behind)-1)
                fin0 = L + rem.sum()
                fin1 = L + mu*len(rem) + s*(rem.sum()-mu*len(rem))
                f = lambda x: 1.0 if x>0 else (0.5 if x==0 else 0.0)
                base.append(f(fin0)); new.append(f(fin1))
    n=len(base); d=np.array(new)-np.array(base)
    return np.mean(base), np.mean(new), n
for k in (200,300):
    for sa,sb in ((0.7,1.0),(1.0,1.3),(0.7,1.3),(0.5,1.5)):
        b,nw,n = run(k,sa,sb)
        print(f"k={k} scale ahead {sa} behind {sb}: score {b:.3f} -> {nw:.3f}  (+{nw-b:.3f}) over {n} matches")
