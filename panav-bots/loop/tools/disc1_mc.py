"""Prototype of the replacement discard rule, scored offline on disc1_eval rows.
  disc1_mc.py rows.json [--delta D] [--m M] [--max N]
rule: keep the pair with the highest S1; if another keep has S1 within DELTA of the best, break the near-tie with an M-sample
Monte Carlo equity vs a random 2-card hand over random turn+river (common random numbers)."""
import argparse, json, time
import numpy as np
import disc1_lib; disc1_lib.install()
import d1_lib as L
from d1_discard import KEEPS
from disc1_eval import ev

def pick(hole3, flop, s1, delta, M, rng):
    top = int(np.argmax(s1))
    cand = [i for i in range(3) if s1[i] >= s1[top] - delta]
    if len(cand) == 1:
        return top, 0
    unseen = np.array([c for c in range(52) if c not in hole3 and c not in flop])
    pk = unseen[np.argsort(rng.random((M, len(unseen))), axis=1)[:, :4]]
    opp, runs = pk[:, :2], pk[:, 2:]
    e = {}
    for i in cand:
        k = np.array([hole3[j] for j in KEEPS[i]], dtype=np.int64)
        e[i] = ev(np.tile(k, (M, 1)), opp, runs, flop).mean()
    return max(cand, key=lambda i: (e[i], s1[i])), 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("rows"); ap.add_argument("--delta", type=float, default=0.1)
    ap.add_argument("--m", type=int, default=1000); ap.add_argument("--max", type=int, default=1200)
    a = ap.parse_args()
    rows = json.load(open(a.rows))[:a.max]
    rng = np.random.default_rng(5)
    def loss(x, k, m="opt"):
        A = np.array(x["eqA_" + m]); B = np.array(x["eqB_" + m])
        return 0.5 * ((B[A.argmax()] - B[k]) + (A[B.argmax()] - A[k]))
    out = []; used = 0; t = time.time()
    for x in rows:
        k, u = pick(L.cards(x["hole3"]), L.cards(x["flop"]), x["s1"], a.delta, a.m, rng)
        out.append(loss(x, k)); used += u
    dt = time.time() - t
    s = lambda v: f"{100 * np.mean(v):.2f} +-{100 * np.std(v, ddof=1) / np.sqrt(len(v)):.2f}"
    print(f"delta={a.delta} M={a.m} n={len(rows)} loss_opt={s(out)} (slot0 {s([loss(x, x['slot'].index(0)) for x in rows])}) MC used {used / len(rows):.2f}  {1000 * dt / len(rows):.2f} ms/discard avg")
