"""RD: fit the own-range betting model (bot/strategy/own_range.py `OWN_BET`) on traced river hands (lab/rd_trace.py).

    .venv/bin/python -m lab.rd_fit_own logs/rd/fit_*.pkl [--ridge 1.0]

Our own bet / call / check / raise / fold choices, given the strength percentile of our REAL hand at that moment
(the same `Inference.strength` the range uses), as a multinomial logit per (board size, facing): logit_k = a_k + b_k s.
Held-out check = cross-fit by trace file; the criterion is the mean log-likelihood per decision of what we did.
Prints the table to paste into own_range.py and the beta of the discard softmax (grid over the traces' discards).
"""
import argparse
import collections
import pickle

import numpy as np
from scipy.optimize import minimize

KINDS = ("F", "K", "C", "R")


def cells(recs):
    """(nboard, facing) -> list of (legal kinds, action kind, s)."""
    out = collections.defaultdict(list)
    for r in recs:
        for d in r["own_dec"]:
            if d[0] == "bet":
                _, nb, legal, act, s = d
                out[(nb, "C" in legal or "F" in legal)].append((tuple(legal), act, s))
    return out


def nll(theta, data, ridge):
    a = theta[:4]; b = theta[4:]
    tot = 0.0
    for legal, act, s in data:
        idx = [KINDS.index(k) for k in legal]
        z = a[idx] + b[idx] * s
        z = z - z.max()
        tot -= z[legal.index(act)] - np.log(np.exp(z).sum())
    return tot + ridge * float(np.sum(b ** 2) + np.sum(a ** 2))


def fit(data, ridge):
    r = minimize(nll, np.zeros(8), args=(data, ridge), method="L-BFGS-B")
    return r.x


def ll(theta, data):
    return -nll(theta, data, 0.0) / max(1, len(data))


def baseline_default(data):
    """The shipped generic model: logit = 3 * slope * (s - pivot)."""
    from bot.sim.inference import BET_MODEL
    t = 0.0
    for legal, act, s in data:
        z = np.array([3.0 * BET_MODEL[k][0] * (s - BET_MODEL[k][1]) for k in legal])
        z -= z.max()
        t += z[legal.index(act)] - np.log(np.exp(z).sum())
    return t / max(1, len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--ridge", type=float, default=1.0)
    a = ap.parse_args()
    per = [pickle.load(open(f, "rb")) for f in a.files]
    allrecs = [r for p in per for r in p]
    print(f"{len(allrecs)} river hands from {len(per)} files")
    cl = cells(allrecs)
    table = {}
    for key in sorted(cl):
        data = cl[key]
        # leave-one-file-out predictive log-lik vs the default model
        cv = []
        for i in range(len(per)):
            tr = [x for j, p in enumerate(per) if j != i for x in cells(p).get(key, [])]
            te = cells(per[i]).get(key, [])
            if len(tr) > 20 and te:
                cv.append((ll(fit(tr, a.ridge), te), len(te), baseline_default(te)))
        th = fit(data, a.ridge)
        w = sum(n for _, n, _ in cv) or 1
        print(f"board {key[0]} facing {key[1]}: n={len(data)} fit ll {ll(th, data):+.3f}, default ll {baseline_default(data):+.3f}"
              f" | cross-fit {sum(x * n for x, n, _ in cv) / w:+.3f} vs default {sum(y * n for _, n, y in cv) / w:+.3f}")
        kinds = sorted({k for legal, _, _ in data for k in legal}, key=KINDS.index)
        table[key] = {k: (round(float(th[KINDS.index(k)]), 2), round(float(th[4 + KINDS.index(k)]), 2)) for k in kinds}
    print("OWN_BET =", table)
    # discard softmax beta
    dis = [d for r in allrecs for d in r["own_dec"] if d[0] == "discard"]
    for beta in (0.5, 1, 2, 3, 4.5, 6, 9, 12):
        t = 0.0
        for _, ss, ch in dis:
            z = beta * np.array(ss); z -= z.max()
            t += z[ch] - np.log(np.exp(z).sum())
        print(f"discard beta {beta}: mean ll {t / max(1, len(dis)):+.4f} over {len(dis)}")


if __name__ == "__main__":
    main()
