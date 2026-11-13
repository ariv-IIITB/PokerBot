"""D1 node records: one row per decision of the logged bot (action_requests), with size, strength and realised chips.

  PYTHONPATH=panav-bots/loop/tools .venv/bin/python panav-bots/loop/tools/d1_nodes.py OUT.json label=DIR [label=DIR ...] [--samples S]

Row fields: bot, seat, street, hand (file:id), facing (to_call>0), kind (open / raise / none), f (size as pot fraction,
translate's definition: opening bet X/pot_before, raise (X-our_bet)/(pot_before+their_to_call)), allin (opp all-in),
pot, to_call, committed (chips we put in before the decision), act (fold/call/check/raise), eq (our equity vs a random
opponent hand; best of the 3 keeps while we still hold 3 cards), out (= net + committed: what the rest of the hand paid
from this decision on; fold = 0), net, ending (how the hand ended).  Hand-level rows (kind 'hand') carry per-street flows.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

import numpy as np
import d1_lib as L

KEEPS = [(0, 1), (0, 2), (1, 2)]


def equity(mine_sets, board, rng, S):
    """mean equity of the best of several 2-card holdings vs random opp hand + runout (common samples)."""
    known = set(c for m in mine_sets for c in m) | set(board)
    unseen = np.array([c for c in range(52) if c not in known])
    need = 2 + (5 - len(board))
    pick = unseen[np.argsort(rng.random((S, len(unseen))), axis=1)[:, :need]]
    opp, runs = pick[:, :2], pick[:, 2:]
    b = np.tile(np.array(board, dtype=np.int64).reshape(1, -1), (S, 1))
    full = np.concatenate([b, runs], axis=1)
    o = L.evaluate(np.concatenate([opp, full], axis=1))
    best = 0.0
    for m in mine_sets:
        a = L.evaluate(np.concatenate([np.tile(np.array(m, dtype=np.int64), (S, 1)), full], axis=1))
        e = float(np.where(a > o, 1.0, np.where(a == o, 0.5, 0.0)).mean())
        best = max(best, e)
    return best


def size_fraction(r, seat, hist):
    """(kind, f, allin) for the bet/raise we face, from our request r and its history."""
    if r["to_call"] <= 0:
        return "none", None, False
    street = r["street"]; X = r["opp_bet"]; mine = r["my_bet"]
    prev = [a for a in hist if a["street"] == street and a["actor"] == "opp"]
    if len(prev) >= 1:
        # the last opp action in hist is the bet we face; the one before it gives their earlier street bet
        before = [a for a in prev[:-1] if a["action"] in ("raise", "call")]
        p0 = before[-1]["amount"] if before else (0 if street != "preflop" else (1 if seat == "big_blind" else 2))
    else:
        p0 = 0 if street != "preflop" else (1 if seat == "big_blind" else 2)
    pot_r = r["pot"] - (X - p0)                    # pot at the raiser's decision
    tc_r = mine - p0                               # raiser's to_call
    if mine <= p0 or tc_r <= 0:                     # opening bet (nothing of ours to raise over beyond blinds)
        if street == "preflop":
            return "raise", (X - mine) / max(pot_r + max(tc_r, 0), 1), r["opp_stack"] == 0
        return "open", X / max(pot_r, 1), r["opp_stack"] == 0
    return "raise", (X - mine) / max(pot_r + tc_r, 1), r["opp_stack"] == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("dirs", nargs="+")
    ap.add_argument("--samples", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    rows = []
    for spec in a.dirs:
        label, d = spec.split("=", 1)
        for h in L.parse_dir(d):
            res = h["res"]; net = res["net"]; hist = res["history"]; hand = f"{h['file']}:{h['hand_id']}"
            hole3 = L.cards(h["hole3"])
            kept = L.cards(h["dres"]["hole_cards"]) if h["dres"] else None
            last = hist[-1] if hist else {}
            ending = (("WE fold" if last.get("actor") == "me" else "OPP fold") + "@" + str(last.get("street"))
                      if res["result"] == "fold" else "showdown")
            # per-street flow: chips we put in per street (from request/reply states) -> street ledger
            commit = {}
            for r in h["reqs"]:
                rp = r["reply"]
                if rp is None:
                    continue
                board = L.cards(r["board"])
                sets = [list(kept)] if (kept and r["street"] in ("turn", "river")) else [[hole3[i] for i in k] for k in KEEPS]
                eq = equity(sets, board, rng, a.samples)
                kind, f, allin = size_fraction(r, h["seat"], r["history"])
                committed = h["start"] - r["my_stack"]
                rows.append(dict(bot=label, seat=h["seat"], street=r["street"], hand=hand, facing=r["to_call"] > 0, kind=kind,
                                 f=f, allin=allin, pot=r["pot"], to_call=r["to_call"], committed=committed, act=rp["action"],
                                 eq=eq, out=net + committed, net=net, ending=ending, nraise=4 - r.get("raises_left", 4)))
            rows.append(dict(bot=label, seat=h["seat"], street="HAND", hand=hand, net=net, ending=ending))
        print(label, "rows", sum(1 for r in rows if r["bot"] == label), flush=True)
    Path(a.out).write_text(json.dumps(rows))


if __name__ == "__main__":
    main()
