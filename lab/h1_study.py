"""H1: where the chips go against one opponent, from lab.opps.record files with both hands known (lab only).

    .venv/bin/python -m lab.h1_study logs/h1/rec/<opponent>.json.gz [--variant discard_holdem]

Every hand is replayed from its action list (raise amounts are "raise to" street totals; blinds 1/2,
seat 0 = button posts the small blind). The opponent's held cards = dealt minus discarded (lab-only
fields `opp_hole3`, `opp_dis`). Reports, chips per hand unless said:
  * their bets we face, by street and size (bet / pot before it): how often their hand is weak (vs-random
    percentile < 0.5 on the final board), our fold / call / raise share, how often a call wins at the river,
    and the chips of our calls and the counterfactual chips of our folds (call EV = win ? pot_before + bet : -bet).
  * our river bets unfaced, by our strength: their fold / call / raise rate, and how often they call with less.
  * preflop: chips by our first response when they open (we are the big blind) and when they re-raise our open.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict

from bot.game.compile import compile_spec
from bot.strategy.oppstats import hand_percentile
from lab.harness import load_variant

SIZES = ((0.0, 0.4), (0.4, 0.75), (0.75, 1.1), (1.1, 99.0))


def size_label(r: float) -> str:
    for lo, hi in SIZES:
        if lo <= r < hi:
            return f"{lo:.2f}-{hi:.2f}" if hi < 99 else f">{lo:.2f}"
    return "?"


def replay(hand: dict):
    """Yield (street, actor, kind, add, pot_before, tocall_before, hist_index) for every action."""
    seat = hand["seat"]
    me_btn = seat == 0
    total = {"m": 1 if me_btn else 2, "o": 2 if me_btn else 1}
    street_in = dict(total)
    cur = 0
    for i, (street, actor, kind, amount, _choice) in enumerate(hand["h"]):
        if street != cur:
            cur, street_in = street, {"m": 0, "o": 0}
        other = "o" if actor == "m" else "m"
        pot = total["m"] + total["o"]
        tocall = street_in[other] - street_in[actor]
        add = 0
        if kind == "C":
            add = max(0, tocall)
        elif kind == "R" and amount is not None:
            add = int(amount) - street_in[actor]
        yield street, actor, kind, add, pot, tocall, i
        if add > 0:
            street_in[actor] += add
            total[actor] += add


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--variant", default="discard_holdem")
    args = ap.parse_args(argv)
    rules = compile_spec(load_variant(args.variant))
    ev = rules.evaluator
    for path in args.files:
        with gzip.open(path, "rt") as f:
            data = json.load(f)
        hands = [h for p in data["pairs"] for m in p["matches"] for h in m["hands"]]
        n = len(hands)
        print(f"=== {data['opponent']} vs {data['brain']}: {n} hands")
        face = defaultdict(lambda: defaultdict(float))     # (street, size) -> counters
        ourbet = defaultdict(lambda: defaultdict(float))   # strength bucket -> counters
        pre = defaultdict(lambda: [0, 0.0])
        for h in hands:
            board = h["board"]
            opp = [c for c in h.get("opp_hole3", []) if c not in h.get("opp_dis", [])]
            full = len(board) == 5 and len(opp) == 2
            dead = [c for _, cs in h["rv"] for c in cs]
            win = None
            opct = mpct = None
            if full:
                a = ev.evaluate(list(h["hole"]), list(board))
                b = ev.evaluate(opp, list(board))
                win = 1.0 if a > b else (0.5 if a == b else 0.0)
                opct = hand_percentile(ev, opp, board, rules.deck, dead)
                mpct = hand_percentile(ev, h["hole"], board, rules.deck, dead)
            acts = list(replay(h))
            # preflop line
            pf = [x for x in acts if x[0] == 0]
            line = None
            if h["seat"] == 1 and pf and pf[0][1] == "o" and pf[0][2] == "R":
                resp = next((x for x in pf[1:] if x[1] == "m"), None)
                line = "they_open:" + (resp[2] if resp else "?")
            elif h["seat"] == 0 and pf and pf[0][1] == "m" and pf[0][2] == "R":
                resp = next((x for x in pf[1:] if x[1] == "o"), None)
                if resp and resp[2] == "R":
                    ours = next((x for x in pf[2:] if x[1] == "m"), None)
                    line = "we_open_they_3bet:" + (ours[2] if ours else "?")
            if line:
                pre[line][0] += 1
                pre[line][1] += h["delta"]
            for j, (street, actor, kind, add, pot, tocall, i) in enumerate(acts):
                if street == 0:
                    continue
                if actor == "o" and kind == "R":
                    bet = add - max(0, tocall)            # the part over a call
                    pot_b = pot + max(0, tocall)
                    r = bet / max(1, pot_b)
                    resp = next((x for x in acts[j + 1:] if x[1] == "m"), None)
                    if resp is None:
                        continue
                    c = face[(street, size_label(r))]
                    c["n"] += 1
                    c[resp[2]] += 1
                    if opct is not None:
                        c["known"] += 1
                        c["weak"] += opct < 0.5
                    if win is not None and street == 3:
                        ev_call = win * (pot_b + bet) - (1 - win) * bet
                        c["w_n"] += 1
                        c["w_sum"] += win
                        if resp[2] == "C":
                            c["call_ev"] += ev_call
                            c["call_n"] += 1
                            c["call_win"] += win
                        elif resp[2] == "F":
                            c["fold_cf"] += ev_call
                            c["fold_n"] += 1
                            c["fold_win"] += win
                if street == 3 and actor == "m" and kind == "R" and tocall <= 0 and mpct is not None:
                    bucket = "top" if mpct >= 0.8 else ("mid" if mpct >= 0.5 else "weak")
                    resp = next((x for x in acts[j + 1:] if x[1] == "o"), None)
                    if resp is None:
                        continue
                    c = ourbet[(bucket, size_label(add / max(1, pot)))]
                    c["n"] += 1
                    c[resp[2]] += 1
                    if resp[2] != "F" and win is not None:
                        c["called_win"] += win
                        c["called_n"] += 1
        print("-- their bets we face (street size: n | weak share | our F/C/R | river: win if called, our calls n win% EV/call, our folds n would-win% cf EV/fold)")
        for (street, sz), c in sorted(face.items()):
            n0 = c["n"]
            s = f"  st{street} {sz:>9}: n={int(n0):5d} weak={c['weak'] / max(1, c['known']):.2f}" \
                f" F/C/R={c['F'] / n0:.2f}/{c['C'] / n0:.2f}/{c['R'] / n0:.2f}"
            if street == 3 and c["w_n"]:
                s += f" | win={c['w_sum'] / c['w_n']:.2f} calls {int(c['call_n'])} {c['call_win'] / max(1, c['call_n']):.2f}" \
                     f" {c['call_ev'] / max(1, c['call_n']):+.1f} | folds {int(c['fold_n'])} {c['fold_win'] / max(1, c['fold_n']):.2f}" \
                     f" {c['fold_cf'] / max(1, c['fold_n']):+.1f} (total cf {c['fold_cf'] / n:+.3f}/hand)"
            print(s)
        print("-- our unfaced river bets (strength size: n | their F/C/R | we win when called)")
        for (b, sz), c in sorted(ourbet.items()):
            n0 = c["n"]
            print(f"  {b:4} {sz:>9}: n={int(n0):5d} F/C/R={c['F'] / n0:.2f}/{c['C'] / n0:.2f}/{c['R'] / n0:.2f}"
                  f" win|called={c['called_win'] / max(1, c['called_n']):.2f}")
        print("-- preflop lines (our response: n, chips/hand of all hands, chips/pot)")
        for k, (cnt, ch) in sorted(pre.items()):
            print(f"  {k:24} n={cnt:6d} {ch / n:+.3f}/hand {ch / max(1, cnt):+.2f}/pot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
