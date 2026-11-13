"""D1 report tables from d1_discard.py / d1_nodes.py output.

  .venv/bin/python panav-bots/loop/tools/d1_report.py --nodes N.json [--discard D.json] [--section disc|facing|pos|cells|all]
Prints plain-text tables (n, means, SE). Chips are the logged bot's (final). `out` = net + chips already put in.
"""
from __future__ import annotations
import argparse, collections, json, math

import numpy as np

FB = [(0.33, "<=.33"), (0.75, ".33-.75"), (1.2, ".75-1.2"), (2.0, "1.2-2"), (1e9, ">2")]
EB = [(0.35, "eq<.35"), (0.5, ".35-.5"), (0.65, ".5-.65"), (0.8, ".65-.8"), (2, "eq>=.8")]
TREE_MAX = {("flop", "open"): 0.75, ("turn", "open"): 1.0, ("river", "open"): 1.0}


def bk(x, tab):
    for t, n in tab:
        if x <= t + 1e-9:
            return n


def ms(v):
    v = np.asarray(v, float)
    if len(v) == 0:
        return "-", 0.0
    se = v.std(ddof=1) / math.sqrt(len(v)) if len(v) > 1 else float("nan")
    return f"{v.mean():+.2f}±{se:.2f}", se


def discard(rows):
    print("== DISCARD AUDIT (loss = best-keep equity - chosen-keep equity; value = loss x pot at discard)")
    for bot in sorted(set(r["bot"] for r in rows)) + ["ALL"]:
        rs = [r for r in rows if bot == "ALL" or r["bot"] == bot]
        loss = np.array([max(r["eq_rand"]) - r["eq_rand"][r["chosen"]] for r in rs])
        val = loss * np.array([r["pot"] for r in rs])
        act = [r for r in rs if r["eq_act"]]
        la = np.array([max(r["eq_act"]) - r["eq_act"][r["chosen"]] for r in act]) if act else np.array([0.0])
        print(f"{bot:14s} n={len(rs):5d} | vs random: share>=3pts {np.mean(loss >= .03):.3f} (>=6pts {np.mean(loss >= .06):.3f}) "
              f"mean loss {100 * loss.mean():.2f} pts, {val.mean():.2f} chips/discard | vs actual opp (showdowns n={len(act)}): "
              f"share>=3pts {np.mean(la >= .03):.3f}, mean loss {100 * la.mean():.2f} pts")
    rs = rows
    print("-- by chosen-keep type (ALL bots): n, share>=3pts, mean loss pts, chips/discard")
    g = collections.defaultdict(list)
    for r in rs:
        g[r["type"]].append(r)
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1]))[:14]:
        l = np.array([max(r["eq_rand"]) - r["eq_rand"][r["chosen"]] for r in v])
        print(f"  {k:22s} n={len(v):5d} {np.mean(l >= .03):.3f} {100 * l.mean():5.2f} {np.mean(l * [r['pot'] for r in v]):.2f}")
    print("-- by seat (ALL)")
    for s in ("button", "big_blind"):
        v = [r for r in rs if r["seat"] == s]
        l = np.array([max(r["eq_rand"]) - r["eq_rand"][r["chosen"]] for r in v])
        print(f"  {s:10s} n={len(v)} share>=3pts {np.mean(l >= .03):.3f} mean {100 * l.mean():.2f} pts, {np.mean(l * [r['pot'] for r in v]):.2f} chips/discard")
    print("-- where best keep differs: chosen type -> best type (top 8 mistakes >=3pts, ALL)")
    c = collections.Counter((r["type"], r["best_type"]) for r in rs if max(r["eq_rand"]) - r["eq_rand"][r["chosen"]] >= .03)
    for (a, b), n in c.most_common(8):
        print(f"  {a:20s} -> {b:20s} {n}")


def facing(rows):
    print("== FACING A BET: response mix, strength, realised chips from the decision on (per bucket)")
    d = [r for r in rows if r["street"] != "HAND" and r["facing"]]
    for scope in ("ALL", "lakshya1"):
        print(f"-- scope {scope}")
        print("street seat bucket     n   fold/call/raise  eq(fold) eq(call) eq(raise) | out(call) out(raise)  [mean±SE, n]")
        for st in ("preflop", "flop", "turn", "river"):
            for seat in ("button", "big_blind"):
                for _, b in FB:
                    v = [r for r in d if r["street"] == st and r["seat"] == seat and bk(r["f"], FB) == b and (scope == "ALL" or r["bot"] == scope)]
                    if len(v) < 25:
                        continue
                    A = {a: [r for r in v if r["act"] == a] for a in ("fold", "call", "raise")}
                    mix = "/".join(f"{len(A[a]) / len(v):.2f}" for a in A)
                    eqs = [f"{np.mean([r['eq'] for r in A[a]]):.2f}" if A[a] else "  - " for a in A]
                    oc = ms([r["out"] for r in A["call"]])[0]; orr = ms([r["out"] for r in A["raise"]])[0]
                    print(f"{st:7s} {seat[:3]} {b:8s} {len(v):5d}  {mix:14s}  {eqs[0]}  {eqs[1]}  {eqs[2]}   | {oc} (n={len(A['call'])})  {orr} (n={len(A['raise'])})")
    print("-- INSIDE vs ABOVE our tree's biggest non-allin size (postflop opening bets; flop .75, turn/river 1.0; allin separate)")
    for scope in ("ALL", "lakshya1"):
        for st in ("flop", "turn", "river"):
            v = [r for r in d if r["street"] == st and r["kind"] == "open" and (scope == "ALL" or r["bot"] == scope)]
            for name, sel in (("inside", lambda r: not r["allin"] and r["f"] <= TREE_MAX[(st, "open")] + 0.12),
                              ("above", lambda r: not r["allin"] and r["f"] > TREE_MAX[(st, "open")] + 0.12),
                              ("allin", lambda r: r["allin"])):
                w = [r for r in v if sel(r)]
                if len(w) < 20:
                    continue
                n = len(w)
                A = {a: [r for r in w if r["act"] == a] for a in ("fold", "call", "raise")}
                print(f"{scope:8s} {st:6s} {name:6s} n={n:5d} fold/call/raise {len(A['fold']) / n:.2f}/{len(A['call']) / n:.2f}/{len(A['raise']) / n:.2f} "
                      f"eq(call) {np.mean([r['eq'] for r in A['call']]) if A['call'] else 0:.2f} out(call) {ms([r['out'] for r in A['call']])[0]} "
                      f"out(raise) {ms([r['out'] for r in A['raise']])[0]} | eq(fold) {np.mean([r['eq'] for r in A['fold']]) if A['fold'] else 0:.2f}")


def pos(rows):
    print("== POSITION: chips/hand by seat per opponent; by ending; value of reaching each street (mean out of first decision on it)")
    for bot in sorted(set(r["bot"] for r in rows)):
        H = [r for r in rows if r["bot"] == bot and r["street"] == "HAND"]
        line = []
        for seat in ("button", "big_blind"):
            v = [r["net"] for r in H if r["seat"] == seat]
            line.append(f"{seat[:3]} {ms(v)[0]} (n={len(v)})")
        print(f"{bot:14s} " + " | ".join(line))
        for seat in ("button", "big_blind"):
            e = collections.defaultdict(list)
            for r in H:
                if r["seat"] == seat:
                    e[r["ending"]].append(r["net"])
            tot = len([r for r in H if r["seat"] == seat])
            bits = [f"{k} {sum(v) / tot:+.2f}" for k, v in sorted(e.items(), key=lambda kv: sum(kv[1]) / tot)]
            print(f"   {seat[:3]} by ending (chips/hand of seat): " + "; ".join(bits))
    print("-- value of entering each street, ALL bots (mean over hands reaching it of net + chips committed before)")
    first = {}
    for r in rows:
        if r["street"] != "HAND":
            first.setdefault((r["bot"], r["hand"], r["street"]), r)
    for seat in ("button", "big_blind"):
        out = []
        for st in ("flop", "turn", "river"):
            v = [r["out"] for (b, h, s), r in first.items() if s == st and r["seat"] == seat]
            out.append(f"{st} {ms(v)[0]} (n={len(v)})")
        print(f"  {seat[:3]}: " + "  ".join(out))


def cells(rows, top=12):
    d = [r for r in rows if r["street"] != "HAND"]
    bots = sorted(set(r["bot"] for r in d))
    # Table A (robust): we face a bet and CONTINUE (call/raise). Fold is always available and pays exactly 0, so
    # a cell whose realised chips are negative lost that much against folding. loss = -sum(out).
    g = collections.defaultdict(list)
    for r in d:
        if r["facing"] and r["act"] in ("call", "raise"):
            g[(r["street"], r["seat"], bk(r["f"], FB), bk(r["eq"], EB), r["act"])].append(r)
    out = []
    for k, v in g.items():
        if len(v) < 30:
            continue
        o = np.array([r["out"] for r in v], float)
        se = o.std(ddof=1) / math.sqrt(len(o))
        br = sum(1 for b in bots if sum(1 for r in v if r["bot"] == b) >= 10 and np.mean([r["out"] for r in v if r["bot"] == b]) < 0)
        out.append((-o.sum(), k, len(o), o.mean(), se, br, se * len(o)))
    out.sort(key=lambda t: -t[0])
    print("== CELLS A (robust): facing a bet, we continue; loss = -sum(chips from the decision on); fold would pay 0")
    print("rank loss  street seat size    our-eq   act    n    mean±SE        bots-losing  SE(total)")
    for i, (loss, k, n, m, se, br, st) in enumerate(out[:top], 1):
        print(f"{i:2d} {loss:7.0f} {k[0]:7s}{k[1][:3]} {k[2]:8s} {k[3]:8s} {k[4]:6s}{n:5d} {m:+7.2f}±{se:.2f}   {br}/{len(bots)}   {st:.0f}")
    # Table B (confounded): same context, compare with the mean of the best other action (hidden info differs).
    ctx = collections.defaultdict(list)
    for r in d:
        fb = bk(r["f"], FB) if r["facing"] else "none"
        ctx[(r["street"], r["seat"], fb, bk(r["eq"], EB))].append(r)
    res = []
    for key, v in ctx.items():
        for act in ("call", "check", "raise"):
            c = [r["out"] for r in v if r["act"] == act]
            if len(c) < 30:
                continue
            alts = [(a2, float(np.mean([r["out"] for r in v if r["act"] == a2])), sum(1 for r in v if r["act"] == a2))
                    for a2 in ("call", "check", "raise") if a2 != act and sum(1 for r in v if r["act"] == a2) >= 30]
            if not alts:
                continue
            alt = max(alts, key=lambda t: t[1])
            res.append((len(c) * (alt[1] - float(np.mean(c))), key, act, len(c), float(np.mean(c)), alt))
    res.sort(key=lambda t: -t[0])
    print("== CELLS B (CONFOUNDED by hidden info: opponent action/board differ between actions): n x (best other mean - cell mean)")
    for i, (loss, key, act, n, m, alt) in enumerate(res[:8], 1):
        print(f"{i:2d} {loss:7.0f} {key[0]:7s}{key[1][:3]} {str(key[2]):8s}{key[3]:8s} {act:6s} n={n:5d} mean {m:+.2f}  alt {alt[0]} {alt[1]:+.2f} (n={alt[2]})")


def ladder(rows, scope="ALL", sizes=("1.2-2", ">2"), streets=("flop", "turn", "river")):
    """For big bets: fold share and call outcome by our-equity bucket. If calls in the lowest populated bucket still pay > 0
    while hands below it are folded, the fold boundary is too tight (extrapolation; selection means calls are the better hands)."""
    print(f"== LADDER ({scope}): facing bets of size in {sizes}: per eq bucket  n, fold%, out(call)")
    d = [r for r in rows if r["street"] != "HAND" and r["facing"] and (scope == "ALL" or r["bot"] == scope)]
    for st in streets:
        for seat in ("button", "big_blind"):
            parts = []
            for _, e in EB:
                v = [r for r in d if r["street"] == st and r["seat"] == seat and bk(r["f"], FB) in sizes and bk(r["eq"], EB) == e]
                if len(v) < 15:
                    continue
                c = [r["out"] for r in v if r["act"] == "call"]
                parts.append(f"{e}: n={len(v)} fold {np.mean([r['act'] == 'fold' for r in v]):.2f} call-out {ms(c)[0]}(n={len(c)})")
            print(f"  {st:6s} {seat[:3]} | " + " | ".join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes"); ap.add_argument("--discard")
    ap.add_argument("--section", default="all")
    a = ap.parse_args()
    if a.discard and a.section in ("all", "disc"):
        discard(json.load(open(a.discard)))
    if a.nodes:
        rows = json.load(open(a.nodes))
        if a.section in ("all", "facing"):
            facing(rows)
        if a.section in ("all", "pos"):
            pos(rows)
        if a.section in ("all", "cells"):
            cells(rows)
        if a.section in ("all", "ladder"):
            ladder(rows)


if __name__ == "__main__":
    main()
