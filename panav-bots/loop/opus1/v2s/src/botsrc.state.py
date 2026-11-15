"""Per-hand state and history replay (BUILDMAP §9.3).

The abstract state is rebuilt from the request's `history` on every request (stateless and robust).
The per-hand cache keeps what the replay cannot know: the slot we chose for each of our own actions
(keyed by its index in the history), the discards, and street features computed once per street.
"""
from shared import betting as B
from shared import cards as C

from . import translate as TR


class HandState:
    def __init__(self, msg, mirror=False):
        self.hand_id = int(msg["hand_id"])
        self.deal = self.hand_id              # hand k of either leg is deal k (the engine's duplicate pairs)
        self.mirror = bool(mirror)            # eval builds: random draws keyed by the deal, unsalted
        seat = msg["seat"]
        if seat not in ("button", "big_blind"):
            raise ValueError(f"bad seat {seat!r}")
        self.seat = 0 if seat == "button" else 1
        self.hole3 = sorted(C.parse_cards(msg["hole_cards"]))
        if len(self.hole3) != 3 or len(set(self.hole3)) != 3:
            raise ValueError("need 3 distinct hole cards")
        self.hole = list(self.hole3)          # 2 cards after the discard
        self.my_discard = None
        self.opp_discard = None
        self.keep_slot = None
        self.my_actions = {}                  # history index -> {street, node, slot, action, amount}
        self.history_after = []               # last history we saw + our reply (for the discard key)
        self.cache = {}                       # street features
        self.small = {}                       # history index -> (x, x_min): opponent raises below our smallest size
        self.translator = make_translator(self)

    def on_discard_result(self, msg):
        self.my_discard = C.parse_card(msg["my_discard"])
        self.opp_discard = C.parse_card(msg["opp_discard"])
        hole = sorted(C.parse_cards(msg["hole_cards"]))
        if len(hole) == 2:
            self.hole = hole

    def on_notice(self, msg):
        # The engine corrected our last action (pitfall §13.4): forget its cached slot, so the replay
        # translates what the engine actually applied.
        if msg.get("code") in ("illegal_action", "malformed") and self.my_actions:
            idx = max(self.my_actions)
            self.my_actions.pop(idx)
            self.cache.get("solver_lik", {}).pop(idx, None)   # the river solver's likelihood of that action

    def record_own(self, req, reply, node_id, slot):
        idx = len(req["history"])
        entry = {"street": req["street"], "actor": "me", "action": reply["action"]}
        if reply["action"] == "raise":
            entry["amount"] = reply["amount"]
        elif reply["action"] == "call":
            entry["amount"] = req["opp_bet"]
        self.my_actions[idx] = {"street": req["street"], "node": node_id, "slot": slot,
                                "action": reply["action"], "amount": reply.get("amount")}
        self.history_after = list(req["history"]) + [entry]


def make_translator(hs):
    def translate(node, opts, amount, max_raise, street=None, index=None, seat=None, req=None, **_):
        if seat == hs.seat:
            mine = hs.my_actions.get(index)
            if mine and mine["action"] == "raise" and mine["amount"] == amount and mine["street"] == street \
                    and mine["node"] == node["id"]:
                if mine["slot"] in node["slots"]:
                    return mine["slot"]
                if isinstance(mine["slot"], str) and mine["slot"].startswith("raise:"):
                    # The river solver's raise (label "raise:<amount>", any size): the nearest size slot,
                    # never allin unless it was all-in. The §9.4 mixture below may map a big or short-stack
                    # raise to allin, and an opponent's raise after it would be off the template.
                    return B.nearest_translate(node, opts, amount, max_raise)
        st = TR.STREET_INDEX.get(street, 9)
        # Release builds: salted per process, so the two legs (same hand_id, same deal) draw independently
        # (Rulebook 10.3); stable within a hand. Seeded eval builds: the deal alone, so both legs mirror.
        key = (hs.deal, st, index) if hs.mirror else (TR.SALT, hs.hand_id, st, index)
        info = {}
        slot, _ = TR.translate_raise(node, opts, amount, req, key, info=info)
        if info.get("below") and index is not None and seat != hs.seat:
            hs.small[index] = (info["x"], info["x_min"])
        return slot
    return translate


def replay(hs, history):
    return B.replay_history(history, hs.seat, translate=hs.translator)
