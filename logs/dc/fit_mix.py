"""DC task 0: fit the 2-rule discard mixture (w, eps) per bot on seeds 9000-9005, score on 9006-9011.
Compares the held-out mean log-likelihood per discard with the current softmax model (beta 6).
Run: .venv/bin/python logs/dc/fit_mix.py"""
import sys, math
import numpy as np
sys.path.insert(0, ".")
from lab.opps import discard_rules as dr, record
from bot.sim import discard as D
from bot.sim.inference import Inference

ev = dr.evaluator()
TRAIN = ["d_conv_opp3", "d_new_rules", "d_new_lag", "d_new_trapper", "d_new_exploiter", "d_new_minraise"]
SPAR = ["starter", "calling_station", "tight", "maniac", "random_legal"]

def cases(name, lo, hi):
    d = record.load(dr.ROOT / "logs/records/s0_9000" / f"{name}.json.gz")
    rows = []
    for p in d["pairs"]:
        if not lo <= p["seed"] <= hi: continue
        for m in p["matches"]:
            for h in m["hands"]:
                h3, dis = h.get("opp_hole3"), h.get("opp_dis") or []
                if h3 is None or len(h3) != 3 or len(dis) != 1 or dis[0] not in h3 or len(h["board"]) < 3: continue
                rows.append((h3, h["board"][:3], h3.index(dis[0])))
    return rows

def arrays(rows):
    return (np.array([r[0] for r in rows], dtype=np.intp), np.array([r[1] for r in rows], dtype=np.intp),
            np.array([r[2] for r in rows]))

def probs(h3, fl, w, eps):
    # board differs per row: loop by unique board is slow; evaluator needs a shared board, so group rows
    out = np.empty((len(h3), 3))
    keys = {}
    for i, f in enumerate(map(tuple, fl)): keys.setdefault(f, []).append(i)
    for f, idx in keys.items():
        out[idx] = D.opp_drop_probs(ev, h3[idx], np.array(f, dtype=np.intp), w, eps)
    return out

def softmax_ll(rows, beta=6.0):
    inf = Inference({"enabled": True, "beta": beta, "ref_hands": 120, "min_ess": .08})
    rng = np.random.default_rng(0)
    # class to hold the object attributes inference needs
    class R: pass
    out = []
    for h3, fl, drop in rows:
        rec = R(); rec.state = R(); rec.state.rules = R(); rec.state.rules.evaluator = ev
        rec.state.rules.deck = list(range(52))
        d = R(); d.options = ("0", "1", "2"); a = R(); a.choice = str(drop); d.action = a
        ll = inf._discard_ll(rec, d, np.array([h3], dtype=np.intp), list(fl), rng)
        out.append(float(ll[0]))
    return np.array(out)

if __name__ == "__main__":
    res = {}
    for name in TRAIN + SPAR:
        tr, te = cases(name, 9000, 9005), cases(name, 9006, 9011)
        if len(tr) < 50: print(name, "too few", len(tr)); continue
        h3, fl, dr_ = arrays(tr)
        best = None
        for w in np.arange(0, 1.01, .1):
            for eps in (0.01, .03, .06, .1, .2, .4, .8):
                p = probs(h3, fl, w, eps)
                ll = np.log(p[np.arange(len(p)), dr_]).mean()
                if best is None or ll > best[0]: best = (ll, w, eps)
        _, w, eps = best
        h3, fl, dr_ = arrays(te)
        p = probs(h3, fl, w, eps)
        llm = np.log(p[np.arange(len(p)), dr_])
        lls = softmax_ll(te[:1500]) ; llm_s = llm[:1500]
        diff = llm_s - lls
        print(f"{name:18s} n_tr={len(tr):5d} n_te={len(te):5d} w={w:.1f} eps={eps:.2f}  LL mix {llm.mean():+.3f}  "
              f"softmax {lls.mean():+.3f} (first 1500)  diff {diff.mean():+.3f} ± {diff.std()/math.sqrt(len(diff)):.3f}", flush=True)
        res[name] = (w, eps)
