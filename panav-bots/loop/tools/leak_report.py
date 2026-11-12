"""Where does bot A lose / win chips? Reads logs written by tools.file_duel --logdir.

  .venv/bin/python panav-bots/loop/tools/leak_report.py DIR [DIR ...]
Breakdown by how the hand ended (who folded on which street / showdown), by seat, by opponent bet size,
plus the opponent's observed frequencies (bet, fold-to-our-bet, raise) per street. Chips are A's (the logged bot's).
"""
from __future__ import annotations
import json, sys, collections
from pathlib import Path

ST = ["preflop", "flop", "turn", "river"]


def hands(dirs):
    for d in dirs:
        for f in sorted(Path(d).glob("*.jsonl")):
            seat = None
            for line in f.read_text().splitlines():
                m = json.loads(line)
                if m["type"] == "new_hand":
                    seat = m.get("seat")
                elif m["type"] == "hand_result":
                    m["seat"] = seat
                    yield m


def main():
    ds = sys.argv[1:]
    end = collections.defaultdict(lambda: [0, 0])         # key -> [n, chips]
    seat = collections.defaultdict(lambda: [0, 0])
    opp = collections.defaultdict(lambda: collections.Counter())
    big = collections.defaultdict(lambda: [0, 0])
    N = tot = 0
    for h in hands(ds):
        N += 1; tot += h["net"]
        hist = h["history"]; last = hist[-1] if hist else {}
        if h["result"] == "fold":
            who = "WE fold" if last.get("actor") == "me" else "OPP folds"
            key = f"{who} @{last.get('street')}"
        else:
            key = "showdown WIN" if h["net"] > 0 else ("showdown LOSS" if h["net"] < 0 else "showdown split")
        end[key][0] += 1; end[key][1] += h["net"]
        seat[h["seat"]][0] += 1; seat[h["seat"]][1] += h["net"]
        # opponent stats: when OPP faces our bet, or opp acts first / checked to
        facing = {s: False for s in ST}
        for a in hist:
            s = a["street"]
            if a["actor"] == "me" and a["action"] in ("raise",):
                facing[s] = True
            elif a["actor"] == "opp":
                if facing[s]:
                    opp[s]["opp_facing_bet"] += 1
                    opp[s]["opp_" + a["action"] + "_vs_bet"] += 1
                    facing[s] = a["action"] == "raise" and False
                else:
                    opp[s]["opp_to_act_unfaced"] += 1
                    opp[s]["opp_" + a["action"] + "_unfaced"] += 1
                if a["action"] == "raise":
                    facing[s] = False
            if a["actor"] == "opp" and a["action"] == "raise":
                facing[s] = False
        # chips lost on big pots (|net| >= 40)
        b = "pot>=40 (|net|)" if abs(h["net"]) >= 40 else "small"
        big[b][0] += 1; big[b][1] += h["net"]
    print(f"hands {N}, net {tot:+d}, {tot / max(N, 1):+.3f} chips/hand")
    print("\nBY ENDING (n, chips, chips/hand-of-all)")
    for k, (n, c) in sorted(end.items(), key=lambda kv: kv[1][1]):
        print(f"  {k:22s} n={n:5d} chips={c:+7d}  {c / max(N, 1):+.3f}/hand")
    print("\nBY SEAT")
    for k, (n, c) in seat.items():
        print(f"  {k:12s} n={n:5d} chips={c:+7d}  {c / max(n, 1):+.3f}/hand")
    print("\nSIZE")
    for k, (n, c) in big.items():
        print(f"  {k:18s} n={n:5d} chips={c:+7d}")
    print("\nOPPONENT TENDENCIES vs us (counts)")
    for s in ST:
        c = opp[s]
        fb = c["opp_facing_bet"]
        ua = c["opp_to_act_unfaced"]
        print(f"  {s:8s} facing our bet n={fb}: fold {c['opp_fold_vs_bet'] / max(fb, 1):.2f} call {c['opp_call_vs_bet'] / max(fb, 1):.2f} "
              f"raise {c['opp_raise_vs_bet'] / max(fb, 1):.2f} | opp first-in n={ua}: bet {c['opp_raise_unfaced'] / max(ua, 1):.2f}")


if __name__ == "__main__":
    main()
