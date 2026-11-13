"""D1 discard audit: equity of each of the 3 possible keeps at every discard decision of the logged bot.

  PYTHONPATH=panav-bots/loop/tools .venv/bin/python panav-bots/loop/tools/d1_discard.py OUT.json label=DIR [label=DIR ...]
            [--max N] [--samples S] [--seed K]

For each discard (our 3 hole cards + the flop; we then keep 2) we compute, with common random numbers across the 3 keeps:
  eq_rand : equity vs a uniform random opponent 2-card hand over random turn+river (S samples; unseen = 46 cards).
  eq_act  : only when the hand reached showdown with the opponent's cards shown: exact enumeration of all turn/river
            runouts vs the opponent's actual kept hand (dead: our 3, flop, opp 2, opp's discard).
Loss = best-keep equity - equity of the keep we chose. Value in chips = loss x pot at the discard (a lower bound: more
money goes in after the discard). Evaluator = the bot's numpy evaluator (best 5 of 7). Writes the per-discard rows.
"""
from __future__ import annotations
import argparse, itertools, json, random
from pathlib import Path

import numpy as np
import d1_lib as L

KEEPS = [(0, 1), (0, 2), (1, 2)]          # kept pair = hole3 without index 2, 1, 0 respectively (discard = the missing one)


def eq_vs(keep2, board, opp, runs):
    """equity of our 2 cards on `board` (list) vs opp rows (N,2) with runouts (N,k)->(N,5-len(board)) ints."""
    N = opp.shape[0]
    b = np.tile(np.array(board, dtype=np.int64), (N, 1))
    full = np.concatenate([b, runs], axis=1)
    me = np.concatenate([np.tile(np.array(keep2, dtype=np.int64), (N, 1)), full], axis=1)
    th = np.concatenate([opp, full], axis=1)
    a = L.evaluate(me); o = L.evaluate(th)
    return np.where(a > o, 1.0, np.where(a == o, 0.5, 0.0))


def hand_type(keep2, flop):
    """Label of the chosen keep on the flop: made hand + draw flag."""
    five = np.array([keep2 + flop], dtype=np.int64)
    cat = int(L.evaluate(five)[0] >> 26)
    r = sorted(c >> 2 for c in keep2); s = [c & 3 for c in keep2]
    fr = [c >> 2 for c in flop]; fs = [c & 3 for c in flop]
    names = {0: "high", 1: "pair", 2: "2pair", 3: "trips", 4: "straight", 5: "flush", 6: "fullhouse", 7: "quads", 8: "sflush"}
    base = names[cat]
    if cat == 1:
        if r[0] == r[1]:
            base = "pocket_pair"
        else:
            pr = [x for x in r if x in fr]
            base = ("board_pair" if not pr else "top_pair" if max(pr) >= max(fr) else "pair_other")
    if cat == 0:
        if s[0] == s[1] and r[1] - r[0] <= 2:
            base = "suited_conn_hi"
        elif r[0] > max(fr):
            base = "overcards"
    # draws (hole card involved)
    draw = ""
    if cat < 5:
        for su in range(4):
            if sum(1 for x in fs if x == su) + sum(1 for x in s if x == su) >= 4 and su in s:
                draw = "+fd"
    if cat < 4:
        ranks = set(r) | set(fr)
        if 12 in ranks:
            ranks.add(-1)
        for lo in range(-1, 9):
            win = set(range(lo, lo + 5))
            if len(win & ranks) >= 4 and (win & set(r) | ({-1} & win if 12 in r else set())):
                draw += "+sd"; break
    return base + draw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("dirs", nargs="+")
    ap.add_argument("--max", type=int, default=4000)
    ap.add_argument("--samples", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    rows = []
    for spec in a.dirs:
        label, d = spec.split("=", 1)
        hs = [h for h in L.parse_dir(d) if h["disc"] and h["dres"]]
        random.Random(a.seed).shuffle(hs)
        hs = hs[:a.max]
        for h in hs:
            hole3 = L.cards(h["disc"]["hole_cards"]); flop = L.cards(h["disc"]["board"])
            dres = h["dres"]; kept = L.cards(dres["hole_cards"]); gone = L.card(dres["my_discard"])
            ci = [i for i, k in enumerate(KEEPS) if sorted(hole3[x] for x in k) == sorted(kept)]
            if len(ci) != 1:
                continue
            ci = ci[0]
            unseen = np.array([c for c in range(52) if c not in hole3 and c not in flop])
            idx = np.argsort(rng.random((a.samples, len(unseen))), axis=1)[:, :4]
            pick = unseen[idx]
            opp, runs = pick[:, :2], pick[:, 2:]
            keeps = [[hole3[i] for i in k] for k in KEEPS]
            er = [float(eq_vs(k, flop, opp, runs).mean()) for k in keeps]
            ea = None
            res = h["res"]
            if res["result"] == "showdown" and res.get("opp_hole_cards") and res.get("opp_discard"):
                oh = L.cards(res["opp_hole_cards"]); od = L.card(res["opp_discard"])
                rest = [c for c in range(52) if c not in hole3 and c not in flop and c not in oh and c != od]
                pr = np.array(list(itertools.combinations(rest, 2)), dtype=np.int64)
                o = np.tile(np.array(oh, dtype=np.int64), (len(pr), 1))
                ea = [float(eq_vs(k, flop, o, pr).mean()) for k in keeps]
            rows.append(dict(bot=label, seat=h["seat"], pot=h["disc"]["pot"], chosen=ci, eq_rand=er, eq_act=ea,
                             type=hand_type(keeps[ci], flop), best_type=hand_type(keeps[int(np.argmax(er))], flop),
                             net=res["net"], hole3=h["disc"]["hole_cards"], flop=h["disc"]["board"], kept=dres["hole_cards"]))
        print(label, "discards audited:", sum(1 for r in rows if r["bot"] == label), flush=True)
    Path(a.out).write_text(json.dumps(rows))


if __name__ == "__main__":
    main()
