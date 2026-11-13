"""DISC1 offline discard-quality evaluator (handles the 'opponent keeps the best of 3 cards' caveat).

  PYTHONPATH=panav-bots/loop/tools .venv/bin/python panav-bots/loop/tools/disc1_eval.py OUT.json label=LOGDIR [...] [--max N] [--samples M]

For every logged discard (our 3 hole cards + flop, flop betting already done) we score each of our 3 keeps by Monte Carlo
(common random numbers) against three opponent models:
  rnd : opponent kept hand = 2 uniformly random cards          (the D1 target)
  opt : opponent holds 3 random cards, keeps the pair with best S1 (flop equity vs random; the bot's own feature)
  act : the opponent's ACTUAL kept hand, exact over all turn/river runouts (showdown hands only; selection-biased)
Samples: M deals of (opp 3 cards, turn, river) from the 46 unseen cards; first half picks the best keep, second half
measures it (and vice versa), so loss = E[eq(best by half A) - eq(chosen)] on half B has no max-of-noise bias.
Rows keep eq vectors so any other keep rule can be re-scored offline (see disc1_rules.py).
"""
from __future__ import annotations
import argparse, itertools, json, random, sys
from pathlib import Path
import numpy as np
import disc1_lib; disc1_lib.install()
import d1_lib as L
import shared.features as F
from d1_discard import hand_type, KEEPS

PAIR_IDX = lambda a, b: b * (b - 1) // 2 + a


def idx2s(h):
    """h (...,3) sorted ascending along last axis -> idx2 of the 3 pairs (a,b),(a,c),(b,c)."""
    a, b, c = h[..., 0], h[..., 1], h[..., 2]
    return np.stack([b * (b - 1) // 2 + a, c * (c - 1) // 2 + a, c * (c - 1) // 2 + b], axis=-1)


def ev(a, b, runs, board):
    """win=1/tie=.5 of hand rows a vs b given runouts (N,2) on 3-card board."""
    N = a.shape[0]
    full = np.concatenate([np.tile(np.array(board, dtype=np.int64), (N, 1)), runs], axis=1)
    x = L.evaluate(np.concatenate([a, full], axis=1)); y = L.evaluate(np.concatenate([b, full], axis=1))
    return np.where(x > y, 1.0, np.where(x == y, 0.5, 0.0))


def score_discard(hole3, flop, rng, M):
    keeps = [np.array([hole3[i] for i in k], dtype=np.int64) for k in KEEPS]
    unseen = np.array([c for c in range(52) if c not in hole3 and c not in flop])
    pick = unseen[np.argsort(rng.random((M, len(unseen))), axis=1)[:, :5]]
    t3 = np.sort(pick[:, :3], axis=1); runs = pick[:, 3:5]
    S1, _ = F.all_features(F.street_rows(flop, True))
    pid = idx2s(t3)                                           # (M,3)
    best = np.argmax(S1[pid], axis=1)                         # opp keeps the pair with the highest S1
    sel = [(0, 1), (0, 2), (1, 2)]
    pa, pb = np.array([s[0] for s in sel]), np.array([s[1] for s in sel])
    opt = np.stack([t3[np.arange(M), pa[best]], t3[np.arange(M), pb[best]]], axis=1)
    rnd = pick[:, :2]
    out = {}
    for name, opp in (("rnd", rnd), ("opt", opt)):
        out[name] = np.stack([ev(np.tile(k, (M, 1)), opp, runs, flop) for k in keeps], axis=1)    # (M,3)
    return out


def split_loss(E, ch):
    """E (M,3) per-sample equities; cross-fitted loss of the chosen keep and the (unbiased) best-keep equity."""
    h = E.shape[0] // 2
    A, B = E[:h], E[h:]
    loss = 0.5 * ((B.mean(0)[A.mean(0).argmax()] - B.mean(0)[ch]) + (A.mean(0)[B.mean(0).argmax()] - A.mean(0)[ch]))
    return float(loss)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("dirs", nargs="+")
    ap.add_argument("--max", type=int, default=100000)
    ap.add_argument("--samples", type=int, default=8000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    rows = []
    for spec in a.dirs:
        label, d = spec.split("=", 1)
        hs = [h for h in L.parse_dir(d) if h["disc"] and h["dres"]]
        random.Random(a.seed).shuffle(hs); hs = hs[:a.max]
        for h in hs:
            hole3 = L.cards(h["disc"]["hole_cards"]); flop = L.cards(h["disc"]["board"])
            dres = h["dres"]; kept = L.cards(dres["hole_cards"])
            ci = [i for i, k in enumerate(KEEPS) if sorted(hole3[x] for x in k) == sorted(kept)]
            if len(ci) != 1:
                continue
            ci = ci[0]
            sc = score_discard(hole3, flop, rng, a.samples)
            row = dict(bot=label, seat=h["seat"], pot=h["disc"]["pot"], chosen=ci, hole3=h["disc"]["hole_cards"],
                       flop=h["disc"]["board"], net=h["res"]["net"], seed=h["seed"], leg=h["leg"])
            for k, E in sc.items():
                row["eq_" + k] = [float(x) for x in E.mean(0)]
                hh = E.shape[0] // 2
                row["eqA_" + k] = [float(x) for x in E[:hh].mean(0)]; row["eqB_" + k] = [float(x) for x in E[hh:].mean(0)]
                row["loss_" + k] = split_loss(E, ci)
            # type of chosen / best-by-opt keep
            keeps = [[hole3[i] for i in k] for k in KEEPS]
            row["type"] = hand_type(keeps[ci], flop)
            row["best_opt"] = int(np.argmax(row["eq_opt"])); row["type_best"] = hand_type(keeps[row["best_opt"]], flop)
            # blueprint context: S1 of each keep, slot rank of each keep, b3, pot class
            th = disc1_lib.blueprint()[1]; potclass = disc1_lib.blueprint()[3]
            h3s = sorted(hole3); pairs = F.hand_pairs(h3s)
            feats = F.own_features(F.street_rows(flop, True), pairs)
            b3, slots = F.bucket3(h3s, [x[0] for x in feats], [x[1] for x in feats], th)
            s1 = {pairs[i]: feats[i][0] / 97290.0 for i in range(3)}
            kp = [tuple(sorted(hole3[i] for i in k)) for k in KEEPS]
            row["s1"] = [s1[p] for p in kp]; row["slot"] = [slots.index(p) for p in kp]
            row["b3"] = int(b3); row["pc"] = int(potclass(h["disc"]["pot"]))
            # flop betting: who put chips in on the flop (from the full history)
            fh = [x for x in h["res"]["history"] if x["street"] == "flop"]
            row["flop_me_bet"] = sum(1 for x in fh if x["actor"] == "me" and x["action"] in ("bet", "raise"))
            fb = [x["actor"] for x in fh if x["action"] in ("bet", "raise")]
            row["flop_last_aggr"] = fb[-1] if fb else "none"
            row["flop_opp_bet"] = sum(1 for x in fh if x["actor"] == "opp" and x["action"] in ("bet", "raise"))
            # actual showdown hand
            res = h["res"]
            if res["result"] == "showdown" and res.get("opp_hole_cards") and res.get("opp_discard"):
                oh = L.cards(res["opp_hole_cards"]); od = L.card(res["opp_discard"])
                rest = [c for c in range(52) if c not in hole3 and c not in flop and c not in oh and c != od]
                pr = np.array(list(itertools.combinations(rest, 2)), dtype=np.int64)
                o = np.tile(np.array(oh, dtype=np.int64), (len(pr), 1))
                ea = [float(ev(np.tile(np.array(k, dtype=np.int64), (len(pr), 1)), o, pr, flop).mean()) for k in keeps]
                row["eq_act"] = ea; row["loss_act"] = max(ea) - ea[ci]
            rows.append(row)
        print(label, "discards:", sum(1 for r in rows if r["bot"] == label), flush=True)
        Path(a.out).write_text(json.dumps(rows))


if __name__ == "__main__":
    main()
