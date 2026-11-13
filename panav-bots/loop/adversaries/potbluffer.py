"""potbluffer (call1 adversary): exploits a bot that folds too much to pot-size bets, or one that calls them too much
(an exploiter of potfold would do exactly this). Stdlib only (hand scoring from the spar helper, also stdlib).

  postflop, nothing to call: bets 0.75-1.0 pot on EVERY street. Value with equity >= 0.55 vs a random hand; with a weaker
  hand it bets anyway (BLUFF_P) so about half of its bets are bluffs.
  postflop, facing a bet or raise: folds unless equity >= 0.60; never raises.   (so it folds to raises)
  preflop: raises 3x with 75%, else calls; facing a raise it calls 60% and folds 40%; never re-raises.
Debug counters go to stderr at match_end.
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "eval_bots", "spar"))
from common import card_to_int, int_to_card, score  # noqa: E402

BLUFF_P = 0.85
rng = random.Random()
ALL = list(range(52))
stats = {"bets": 0, "value": 0, "bluff": 0, "fold_to_raise": 0}


def equity(hole, board, samples=40):
    known = set(hole) | set(board)
    unseen = [c for c in ALL if c not in known]
    win = 0.0
    for _ in range(samples):
        pick = rng.sample(unseen, 2 + 5 - len(board))
        opp, run = pick[:2], pick[2:]
        full = board + run
        a, b = score(hole + full), score(opp + full)
        win += 1.0 if a > b else 0.5 if a == b else 0.0
    return win / samples


def best_pair(hole3, board):
    best, pair = -1, None
    for i in range(3):
        keep = [c for j, c in enumerate(hole3) if j != i]
        s = score(keep + board)
        if s > best:
            best, pair = s, keep
    return pair


def raise_to(req, x):
    return {"type": "action", "action": "raise", "amount": int(min(max(x, req["min_raise"]), req["max_raise"]))}


def act(req, hole):
    legal, tc = req["legal_actions"], req["to_call"]
    if req["street"] == "preflop":
        if tc > 0 and req["opp_bet"] > 2:                     # facing a raise
            return {"type": "action", "action": "call" if rng.random() < 0.6 or "fold" not in legal else "fold"}
        if "raise" in legal and rng.random() < 0.75 and req["opp_bet"] <= 2:
            return raise_to(req, 6)
        return {"type": "action", "action": "call" if "call" in legal else "check"}
    board = [card_to_int(c) for c in req["board"]]
    if len(hole) == 3:      # flop betting happens before the discard: best keep
        e = max(equity([c for j, c in enumerate(hole) if j != i], board, 20) for i in range(3))
    else:
        e = equity(hole, board)
    if tc > 0:
        if e >= 0.60 or "fold" not in legal:
            return {"type": "action", "action": "call"}
        stats["fold_to_raise"] += 1
        return {"type": "action", "action": "fold"}
    value = e >= 0.55
    if "raise" in legal and (value or rng.random() < BLUFF_P):
        stats["bets"] += 1
        stats["value" if value else "bluff"] += 1
        return raise_to(req, rng.uniform(0.75, 1.0) * req["pot"])
    return {"type": "action", "action": "check" if "check" in legal else "call"}


def main():
    hole = []
    for line in sys.stdin:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        t, reply = m.get("type"), None
        try:
            if t == "new_hand":
                hole = [card_to_int(c) for c in m["hole_cards"]]
            elif t == "discard_request":
                h3 = [card_to_int(c) for c in m["hole_cards"]]
                board = [card_to_int(c) for c in m.get("board", [])]
                keep = best_pair(h3, board)
                drop = [c for c in h3 if c not in keep][0]
                hole = keep
                reply = {"type": "discard", "card": int_to_card(drop)}
            elif t == "action_request":
                reply = act(m, hole)
            elif t == "match_end":
                print(f"potbluffer stats {stats}", file=sys.stderr, flush=True)
                break
        except Exception as exc:
            print("error", repr(exc), file=sys.stderr, flush=True)
            if t == "action_request":
                reply = {"type": "action", "action": "fold" if "fold" in m["legal_actions"] else "check" if "check" in m["legal_actions"] else "call"}
            elif t == "discard_request":
                reply = {"type": "discard", "card": m["hole_cards"][0]}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
