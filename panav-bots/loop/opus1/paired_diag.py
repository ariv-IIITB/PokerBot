"""OPUS1: paired per-hand diagnosis of two bots run on the SAME deals (file_duel, same --first-seed).

  .venv/bin/python panav-bots/loop/opus1/paired_diag.py LOGDIR_A LOGDIR_B [--top 0]

For every (seed, leg, hand) both logs contain, the hand's net for A and B is compared. The hand is attributed to
its FIRST DIVERGENCE: the first point where the two bots did something different (discard, or an action at a
decision point with the same public history). Output: chips summed by divergence class (A's net - B's net), with
counts, plus the probe-spot table (opponent checked first on a street, we bet) for each bot: how often, and how
the opponent answered (fold / call / raise) and what those hands netted.
Deals are identical, but both bots sample mixed strategies, so many divergences are pure noise; classes that the
probe / DISC1 create are the ones whose count is clearly asymmetric (A bets / B checks vs the reverse).
"""
from __future__ import annotations
import json, sys
from collections import defaultdict
from pathlib import Path


def load(d: Path):
    out = {}
    for f in sorted(d.glob("seed*_m*.jsonl")):
        seed, leg = f.stem.split("_")
        hands = {}
        for line in f.open():
            m = json.loads(line)
            t = m.get("type")
            if t == "discard_result":
                hands.setdefault(m["hand_id"], {})["disc"] = m.get("my_discard")
            elif t == "hand_result":
                h = hands.setdefault(m["hand_id"], {})
                h["net"] = m.get("net", 0)
                h["hist"] = m.get("history") or []
                h["res"] = m.get("result")
        for hid, h in hands.items():
            if "net" in h:
                out[(seed, leg, hid)] = h
    return out


def seq(h):
    """The hand as a list of tokens: actions (actor, street, action, amount) with the discard put before the
    first flop action."""
    toks, disc_done = [], False
    for e in h["hist"]:
        if e.get("street") != "preflop" and not disc_done:
            toks.append(("me", "discard", "discard", h.get("disc")))
            disc_done = True
        toks.append((e.get("actor"), e.get("street"), e.get("action"), e.get("amount")))
    return toks


def bucket_amt(street, tok, prev):
    a = tok[2]
    return a if a != "raise" else "bet" if not any(p[1] == street and p[2] == "raise" for p in prev) else "raise"


def diverge(ha, hb):
    sa, sb = seq(ha), seq(hb)
    for i in range(min(len(sa), len(sb))):
        if sa[i] != sb[i]:
            ta, tb = sa[i], sb[i]
            prev = sa[:i]
            if ta[1] == "discard":
                return "discard"
            if ta[0] != tb[0] or ta[1] != tb[1]:
                return "other"
            who = "us" if ta[0] == "me" else "opp"
            st = ta[1]
            line = [p[2] for p in prev if p[1] == st]
            opp_checked = line == ["check"] and st != "preflop"
            ca, cb = bucket_amt(st, ta, prev), bucket_amt(st, tb, prev)
            ctx = "afterOppCheck" if opp_checked else ("first" if not line else "/".join(line))
            if ca == cb:      # same action, different size
                return f"{who} {st} {ctx}: size"
            return f"{who} {st} {ctx}: A {ca} / B {cb}"
    return None if len(sa) == len(sb) else "other"


def probe_spots(H):
    """Per bot: spots where the opp checked first on a postflop street and we bet; the opponent's answer."""
    res = defaultdict(lambda: [0, 0])   # (street, answer) -> [n, net]
    for h in H.values():
        hist = h["hist"]
        for st in ("flop", "turn", "river"):
            line = [e for e in hist if e.get("street") == st]
            if len(line) >= 2 and line[0]["actor"] == "opp" and line[0]["action"] == "check" and line[1]["actor"] == "me" \
                    and line[1]["action"] == "raise":
                ans = line[2]["action"] if len(line) > 2 else "?"
                r = res[(st, ans)]
                r[0] += 1
                r[1] += h["net"]
                break
    return res


def main():
    da, db = Path(sys.argv[1]), Path(sys.argv[2])
    A, B = load(da), load(db)
    keys = sorted(set(A) & set(B))
    cls = defaultdict(lambda: [0, 0, 0, 0, 0])  # n, sum dA-B, sum A, sum B, sum (dA-B)^2
    for k in keys:
        c = diverge(A[k], B[k])
        if c is None:
            continue
        r = cls[c]
        r[0] += 1
        r[1] += A[k]["net"] - B[k]["net"]
        r[2] += A[k]["net"]
        r[3] += B[k]["net"]
        r[4] += (A[k]["net"] - B[k]["net"]) ** 2
    tot = sum(A[k]["net"] - B[k]["net"] for k in keys)
    print(f"hands {len(keys)}  total A-B {tot:+d} chips ({tot / max(1, len(keys)):+.3f}/hand)  A {sum(A[k]['net'] for k in keys):+d}"
          f"  B {sum(B[k]['net'] for k in keys):+d}")
    print(f"{'divergence class':52s} {'n':>5s} {'A-B':>7s} {'se':>5s} {'A':>7s} {'B':>7s}")
    for c, r in sorted(cls.items(), key=lambda kv: kv[1][1]):
        if r[0] >= 5 or abs(r[1]) >= 100:
            se = (max(0.0, r[4] - r[1] ** 2 / r[0])) ** 0.5
            print(f"{c:52s} {r[0]:5d} {r[1]:+7d} {se:5.0f} {r[2]:+7d} {r[3]:+7d}")
    for name, H in (("A", A), ("B", B)):
        ps = probe_spots({k: H[k] for k in keys})
        print(f"-- {name}: we bet after the opponent checked (first such street per hand): answer n net")
        for st in ("flop", "turn", "river"):
            row = [f"{ans} {ps[(st, ans)][0]:4d} {ps[(st, ans)][1]:+6d}" for ans in ("fold", "call", "raise")]
            print(f"   {st:5s} " + " | ".join(row))


if __name__ == "__main__":
    main()
