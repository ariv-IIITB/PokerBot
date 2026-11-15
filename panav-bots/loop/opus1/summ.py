"""OPUS1 summary: MATCH WINS first, then chips/hand, paired by seed.

  .venv/bin/python panav-bots/loop/opus1/summ.py CAND.json [BASE.json]
A match = one duplicate pair; win if total chips over both legs > 0, draw (== 0) 0.5.
With BASE: paired difference cand - base over the seeds both contain (wins in pp, chips/hand), SE over seeds.
"""
from __future__ import annotations
import json, math, sys


def load(p):
    d = json.load(open(p))
    return {r["seed"]: r for r in d["pairs"]}, d


def win(r):
    return 1.0 if r["chips"] > 0 else 0.5 if r["chips"] == 0 else 0.0


def cph(r):
    return r["chips"] / max(1, r["hands"])


def mse(xs):
    n = len(xs)
    m = sum(xs) / n
    se = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n) if n > 1 else float("nan")
    return m, se


def one(p):
    P, _ = load(p)
    rs = list(P.values())
    w = sum(win(r) for r in rs)
    m, se = mse([cph(r) for r in rs])
    ff = sum(r.get("ff_a", 0) for r in rs), sum(r.get("ff_b", 0) for r in rs)
    return dict(n=len(rs), w=w, pct=100 * w / len(rs), cph=m, se=se, ff=ff)


def paired(pc, pb):
    C, _ = load(pc)
    B, _ = load(pb)
    ks = sorted(set(C) & set(B))
    dw = [100 * (win(C[k]) - win(B[k])) for k in ks]
    dc = [cph(C[k]) - cph(B[k]) for k in ks]
    return dict(n=len(ks), wc=sum(win(C[k]) for k in ks), wb=sum(win(B[k]) for k in ks), dw=mse(dw), dc=mse(dc),
                dws=dw, dcs=dc, keys=ks)


def fmt1(s):
    return f"{s['w']:g}/{s['n']} ({s['pct']:.0f}%) {s['cph']:+.2f}±{s['se']:.2f} ch/h ff {s['ff'][0]}/{s['ff'][1]}"


if __name__ == "__main__":
    print("cand:", fmt1(one(sys.argv[1])))
    if len(sys.argv) > 2:
        print("base:", fmt1(one(sys.argv[2])))
        p = paired(sys.argv[1], sys.argv[2])
        print(f"paired n={p['n']}: wins {p['wc']:g} vs {p['wb']:g}  dwin {p['dw'][0]:+.1f}±{p['dw'][1]:.1f} pp  "
              f"dchips {p['dc'][0]:+.3f}±{p['dc'][1]:.3f}")
