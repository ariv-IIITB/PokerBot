"""Discard Hold'em bot: protocol layer (JSON lines over stdin/stdout) around the pb.Brain core.

A port of a heads-up Hold'em bot: equity vs a modelled opponent range, range narrowing after
every observed action, bluff frequencies from measured fold rates, a time-bank manager.
Discard Hold'em changes: 3 hole cards (the equity of a hand is its best 2-card keep), a real
discard decision after the flop (sampled equity of each keep against the opponent's range),
and the opponent's revealed discard narrows its range and is out of play.

Run:  python3.11 bot.py        stdout = protocol messages only, debug goes to stderr.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pb.brain import Brain  # noqa: E402
from pb.cards import parse, to_str  # noqa: E402
from pb.types import CALL, CHECK, FOLD, RAISE, HandResult, Obs  # noqa: E402

STREETS = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}
RANK_ORDER = "23456789TJQKA"
SUIT_ORDER = "shdc"


def cards(strs):
    out = []
    for s in strs or ():
        try:
            out.append(parse(s))
        except Exception:
            pass
    return tuple(out)


def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def log(*a):
    try:
        print(*a, file=sys.stderr, flush=True)
    except Exception:
        pass


class Runner:
    def __init__(self):
        self.brain = Brain()
        self.total_hands = 400
        self.bank_s = 60.0
        self.bankroll = 0
        self.seat_button = False
        self.hole = ()
        self.dead = ()
        self.hand_id = 0
        self.hole_strs = []

    # ------------------------------------------------------------ messages
    def on_init(self, m):
        self.total_hands = int(m.get("total_hands", 400))
        self.bank_s = float(m.get("time_bank_ms", 60000)) / 1000.0
        self.brain.new_match(self.total_hands, 60.0 * self.total_hands / 400.0)
        self.brain.clock.initial_bank = self.bank_s
        self.brain.clock.reserve = max(1.5, 0.10 * self.bank_s)

    def on_new_hand(self, m):
        self.hand_id = int(m.get("hand_id", 0))
        self.seat_button = m.get("seat") == "button"
        self.hole_strs = list(m.get("hole_cards", []))
        self.hole = cards(self.hole_strs)
        self.dead = ()
        self.brain.new_hand(self.hand_id, self.hole, self.seat_button)

    def build_obs(self, m):
        legal = set(m.get("legal_actions", []))
        can_raise = "raise" in legal
        board = cards(m.get("board", []))
        return Obs(
            hand_no=int(m.get("hand_id", self.hand_id)), hole=self.hole, board=board,
            street=STREETS.get(m.get("street"), 0), button=self.seat_button,
            pot=int(m["pot"]), hero_pip=int(m["my_bet"]), opp_pip=int(m["opp_bet"]),
            hero_stack=int(m["my_stack"]), opp_stack=int(m["opp_stack"]),
            to_call=int(m.get("to_call", 0)),
            min_raise=int(m.get("min_raise", 0)) if can_raise else 0,
            max_raise=int(m.get("max_raise", 0)) if can_raise else 0,
            can_check="check" in legal, can_raise=can_raise,
            can_call="call" in legal, can_fold="fold" in legal,
            time_left=float(m.get("time_left_ms", self.bank_s * 1000.0)) / 1000.0,
            hands_left=max(1, self.total_hands - self.hand_id + 1),
            bankroll=self.bankroll, big_blind=2, small_blind=1, start_stack=200,
            dead=self.dead)

    def on_action_request(self, m):
        legal = set(m.get("legal_actions", []))
        try:
            obs = self.build_obs(m)
            act = self.brain.act(obs)
            kind = act[0]
            if kind == RAISE and "raise" in legal:
                lo, hi = int(m["min_raise"]), int(m["max_raise"])
                return {"type": "action", "action": "raise", "amount": int(max(lo, min(hi, act[1])))}
            if kind == CHECK and "check" in legal:
                return {"type": "action", "action": "check"}
            if kind == CALL and "call" in legal:
                return {"type": "action", "action": "call"}
            if kind == FOLD and "fold" in legal:
                return {"type": "action", "action": "fold"}
        except Exception as e:
            log("action error", repr(e))
        # last resort: never illegal
        if "check" in legal:
            return {"type": "action", "action": "check"}
        if "call" in legal and int(m.get("to_call", 0)) <= 2:
            return {"type": "action", "action": "call"}
        return {"type": "action", "action": "fold"}

    def on_discard_request(self, m):
        hole_strs = list(m.get("hole_cards", self.hole_strs))
        try:
            hole = cards(hole_strs)
            board = cards(m.get("board", []))
            self.hole = hole
            idx = self.brain.discard(
                hole, board, float(m.get("time_left_ms", self.bank_s * 1000.0)) / 1000.0,
                max(1, self.total_hands - self.hand_id + 1))
            return {"type": "discard", "card": hole_strs[int(idx)]}
        except Exception as e:
            log("discard error", repr(e))
        # last resort: the lowest-ranked card
        low = min(hole_strs, key=lambda c: (RANK_ORDER.index(c[0]), SUIT_ORDER.index(c[1])))
        return {"type": "discard", "card": low}

    def on_discard_result(self, m):
        mine, theirs = cards([m.get("my_discard")]), cards([m.get("opp_discard")])
        hole = cards(m.get("hole_cards", []))
        if mine and theirs and len(hole) == 2:
            self.hole = hole
            self.dead = (mine[0], theirs[0])
            board = self.pending_board
            self.brain.discard_result(mine[0], theirs[0], hole, board)

    def on_hand_result(self, m):
        net = int(m.get("net", 0))
        self.bankroll += net
        opp_hole = cards(m.get("opp_hole_cards") or [])
        board = cards(m.get("board", []))
        hist = m.get("history") or []
        folds = [e for e in hist if e.get("action") == "fold"]
        hero_folded = bool(folds) and folds[-1].get("actor") == "me"
        self.brain.hand_over(HandResult(
            delta=net, opp_hole=opp_hole if len(opp_hole) == 2 else None,
            board=board, hero_folded=hero_folded))

    pending_board = ()

    # ------------------------------------------------------------ loop
    def handle(self, line):
        """One protocol line in; the reply (action or discard) out, or None. Never raises."""
        line = line.strip()
        if not line:
            return None
        try:
            m = json.loads(line)
        except ValueError:
            return None
        if not isinstance(m, dict):
            return None
        t = m.get("type")
        try:
            if t == "init":
                self.on_init(m)
            elif t == "new_hand":
                self.on_new_hand(m)
            elif t == "action_request":
                return self.on_action_request(m)
            elif t == "discard_request":
                self.pending_board = cards(m.get("board", []))
                return self.on_discard_request(m)
            elif t == "discard_result":
                self.on_discard_result(m)
            elif t == "hand_result":
                self.on_hand_result(m)
            elif t == "notice":
                log("notice", m.get("code"), m.get("applied"))
            elif t == "match_end":
                self.over = True
        except Exception as e:  # never let anything escape
            log("handler error", t, repr(e))
            if t == "action_request":
                return {"type": "action", "action": "check" if "check" in m.get("legal_actions", []) else "fold"}
            if t == "discard_request":
                return self.on_discard_request(m)
        return None

    over = False

    def run(self):
        for line in sys.stdin:
            reply = self.handle(line)
            if reply is not None:
                send(reply)
            if self.over:
                break


if __name__ == "__main__":
    try:
        Runner().run()
    except Exception as e:
        log("fatal", repr(e))
