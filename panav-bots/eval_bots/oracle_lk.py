"""ORACLE bot, EVAL ONLY. NEVER SHIP. It cheats on purpose, to give an upper bound for testing.

It finds the match seed from its own first hole cards (the engine deals random.Random(f"{seed}:{deal}").shuffle(deck),
seat 0 = deck[0:3], seat 1 = deck[3:6], board = deck[6:11]), so it knows the opponent's hole cards and the whole board
before anyone acts. After the discards it knows the showdown result exactly. Policy: ahead -> bet and call, behind ->
fold to bets and bluff the river, because lakshya1 folds about 70% of the time to big river bets.
Hand evaluator and keep-score are lakshya1.py's (path in LK_PATH).
"""
import importlib.util
import json
import os
import random
import sys

LK = os.environ.get("LK_PATH", "/Users/panavrg/Downloads/lakshya1.py")
spec = importlib.util.spec_from_file_location("lk", LK)
lk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lk)
CI, CS, ev = lk.CI, lk.CS, lk.ev
RANKS, SUITS = "23456789TJQKA", "shdc"
rng = random.Random(1)


def deal(seed, d):
    deck = [r + s for r in RANKS for s in SUITS]
    random.Random(f"{seed}:{d}").shuffle(deck)
    return deck


class Oracle:
    def __init__(self):
        self.cands = list(range(1, 20001))
        self.seed = None
        self.out = 0

    def new_hand(self, m):
        self.seat, self.hid = m["seat"], m["hand_id"]
        mine = set(m["hole_cards"])
        d = self.hid - 1
        if self.seed is None:
            keep = []
            for s in self.cands:
                dk = deal(s, d)
                if set(dk[0:3] if self.seat == "button" else dk[3:6]) == mine:
                    keep.append(s)
            self.cands = keep
            if len(keep) == 1:
                self.seed = keep[0]
            if not keep:
                self.cands = list(range(1, 20001))
        sd = self.seed if self.seed is not None else (self.cands[0] if self.cands else 1)
        dk = deal(sd, d)
        self.my3 = [CI[c] for c in (dk[0:3] if self.seat == "button" else dk[3:6])]
        self.op3 = [CI[c] for c in (dk[3:6] if self.seat == "button" else dk[0:3])]
        self.board = [CI[c] for c in dk[6:11]]
        self.my2 = self.op2 = None
        self.out = self.expect()

    def keeps(self, h3):
        return [[h3[a] for a in range(3) if a != i] for i in range(3)]

    def likely_op(self):
        i = lk.best_keep_index(self.op3, self.board[:3])
        ks = self.keeps(self.op3)
        return [(ks[j], 0.6 if j == i else 0.2) for j in range(3)]

    @staticmethod
    def sgn(a, b):
        return (a > b) - (a < b)

    def score(self, mine2, ops):
        return sum(w * self.sgn(ev(mine2 + self.board), ev(o + self.board)) for o, w in ops)

    def expect(self):
        ops = self.likely_op()
        return max(self.score(k, ops) for k in self.keeps(self.my3))

    def discard(self):
        ops = self.likely_op()
        best, bi = None, 0
        for i, k in enumerate(self.keeps(self.my3)):
            key = (self.score(k, ops), lk.keep_s(k, self.board[:3]))
            if best is None or key > best:
                best, bi = key, i
        return CS[self.my3[bi]]

    def discard_result(self, m):
        self.my2 = [CI[c] for c in m["hole_cards"]]
        od = CI[m["opp_discard"]]
        self.op2 = [c for c in self.op3 if c != od]
        b = self.board
        self.out = self.sgn(ev(self.my2 + b), ev(self.op2 + b)) if len(self.op2) == 2 else self.expect()

    def act(self, r):
        legal, tc, pot = r["legal_actions"], r["to_call"], r["pot"]
        lo, hi, st = r.get("min_raise", 0), r.get("max_raise", 0), r["street"]

        def raise_to(frac):
            x = int(round(r["opp_bet"] + frac * (pot + tc)))
            return {"type": "action", "action": "raise", "amount": max(lo, min(hi, x))}
        if self.out > 0:                                   # ahead: build the pot, never fold
            if tc > 0:
                return {"type": "action", "action": "call"}
            if "raise" in legal:
                return raise_to(0.6)
            return {"type": "action", "action": "check"}
        if self.out == 0:                                  # chop or unknown: stay cheap
            if "check" in legal:
                return {"type": "action", "action": "check"}
            return {"type": "action", "action": "call" if tc <= 0.25 * pot else "fold"}
        if tc > 0:                                         # behind: give up
            return {"type": "action", "action": "fold"}
        if "raise" in legal and (st == "river" or (st == "turn" and rng.random() < 0.4)):
            return raise_to(1.2 if st == "river" else 1.0)
        return {"type": "action", "action": "check"}


def main():
    o = Oracle()
    for line in sys.stdin:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        t = m.get("type")
        try:
            if t == "new_hand":
                o.new_hand(m)
                continue
            if t == "discard_result":
                o.discard_result(m)
                continue
            if t == "discard_request":
                reply = {"type": "discard", "card": o.discard()}
            elif t == "action_request":
                reply = o.act(m)
            elif t == "match_end":
                break
            else:
                continue
        except Exception:
            lg = m.get("legal_actions", [])
            if t == "discard_request":
                reply = {"type": "discard", "card": m["hole_cards"][0]}
            elif t == "action_request":
                reply = {"type": "action", "action": "check" if "check" in lg else ("call" if "call" in lg else "fold")}
            else:
                continue
        sys.stdout.write(json.dumps(reply, separators=(",", ":")) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
