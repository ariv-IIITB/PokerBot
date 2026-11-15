"""Betting abstraction (BUILDMAP §5.2, Appendix B) and an exact port of engine.Hand.betting_round.

Templates: node dicts {id, kind, bets, facing_allin, actor, slots, child, offset}; actor 0/1 is
first/second to act on the street (preflop: seat = actor; postflop: seat = 1 - actor).
Seats: 0 = button, 1 = big blind.
"""
from collections import namedtuple

OPEN, FACING = "OPEN", "FACING"
END, FOLD = -1, -2
STREETS = ("preflop", "flop", "turn", "river")
STARTING_STACK = 200
SMALL_BLIND = 1
BIG_BLIND = 2
MAX_RAISES = 4
POT_EDGES = (7, 13, 25, 50, 100)
SIZE_SLOTS = ("sizeA", "sizeB", "raise")
SLOT_ACTION = {"fold": "fold", "check": "check", "call": "call",
               "sizeA": "raise", "sizeB": "raise", "raise": "raise", "allin": "raise"}


# ---------------------------------------------------------------- Appendix B: templates

def build_template(preflop):
    nodes = []

    def make(kind, bets, facing_allin, actor, is_root):
        nid = len(nodes); nodes.append(None)
        can_raise = bets < 4 and not facing_allin
        if kind == OPEN:
            slots = ["check"] + (["sizeA", "sizeB", "allin"] if can_raise else [])
        else:
            slots = ["fold", "call"] + (["raise", "allin"] if can_raise else [])
        child = {}
        for s in slots:
            if s == "check":
                child[s] = make(OPEN, bets, False, 1, False) if actor == 0 else END
            elif s == "fold":
                child[s] = FOLD
            elif s == "call":   # the button's preflop limp gives the BB its option
                child[s] = make(OPEN, bets, False, 1, False) if (preflop and is_root) else END
            else:
                child[s] = make(FACING, bets + 1, s == "allin", 1 - actor, False)
        nodes[nid] = dict(id=nid, kind=kind, bets=bets, facing_allin=facing_allin,
                          actor=actor, slots=slots, child=child)
        return nid
    if preflop:
        make(FACING, 1, False, 0, True)
    else:
        make(OPEN, 0, False, 0, True)
    offset = 0
    for n in nodes:
        n["offset"] = offset; offset += len(n["slots"])
    return nodes, offset


POST, POST_SLOTS = build_template(False)
PRE, PRE_SLOTS = build_template(True)
assert (len(POST), POST_SLOTS) == (32, 92)
assert (len(PRE), PRE_SLOTS) == (19, 54)


def template_for(street):
    return PRE if street == "preflop" else POST


def seat_of_actor(street, actor):
    return actor if street == "preflop" else 1 - actor


# ---------------------------------------------------------------- §4.6, §5.2.3, §5.2.4

def round_half_up(x, num, den):
    """round_half_up(x * num / den) with integer arithmetic."""
    return (x * num + den // 2) // den


def pot_class(pot):
    """bin(pot, POT_EDGES) in [0, 6)."""
    return sum(1 for e in POT_EDGES if e <= pot)


def raw_size(street, node, slot, pot, opp_bet, to_call):
    """Raise-to amount of a size slot before the min_raise clamp (§5.2.3 table)."""
    if street == "preflop":
        if node["kind"] == OPEN:                       # BB after the limp
            return 6 if slot == "sizeA" else 10
        if node["bets"] <= 2:                          # open (bets 1) or 3-bet (bets 2)
            return 3 * opp_bet
        return round_half_up(opp_bet, 9, 4)            # 4-bet (bets 3)
    if node["kind"] == OPEN:
        if street == "flop":
            return round_half_up(pot, 1, 3) if slot == "sizeA" else round_half_up(pot, 3, 4)
        return round_half_up(pot, 1, 2) if slot == "sizeA" else pot
    return opp_bet + pot + to_call                     # postflop pot-size raise


def slot_options(street, node, pot, my_bet, opp_bet, to_call, legal_actions, min_raise, max_raise):
    """[(slot, legal, amount)] in slot order (§5.2.3). amount is the raise-to amount for size and
    allin slots when "raise" is legal (size slots after max(amt, min_raise), even if illegal), else None."""
    can_raise = "raise" in legal_actions
    out, used = [], []
    for slot in node["slots"]:
        if slot in ("fold", "call"):
            out.append((slot, to_call > 0, None))
        elif slot == "check":
            out.append((slot, to_call == 0, None))
        elif slot == "allin":
            out.append((slot, can_raise, max_raise if can_raise else None))
        elif not can_raise:
            out.append((slot, False, None))
        else:
            amt = max(raw_size(street, node, slot, pot, opp_bet, to_call), min_raise)
            ok = (amt < max_raise
                  and 20 * (amt - my_bet) < 17 * (max_raise - my_bet)
                  and amt not in used)
            if ok:
                used.append(amt)
            out.append((slot, ok, amt))
    return out


def slot_options_req(street, node, req):
    return slot_options(street, node, req["pot"], req["my_bet"], req["opp_bet"], req["to_call"],
                        req["legal_actions"], req.get("min_raise"), req.get("max_raise"))


# ---------------------------------------------------------------- engine port (chips)

class StreetState:
    """Exact port of engine.Hand.betting_round for one street. stacks/committed are the hand's
    lists and are updated in place, as in the engine."""

    def __init__(self, street, stacks, committed, hand=None):
        self.street = street
        self.stacks = stacks
        self.committed = committed
        self.hand = hand
        if street == "preflop":
            self.bets, self.last_raise, self.raises, self.actor = [SMALL_BLIND, BIG_BLIND], BIG_BLIND, 1, 0
        else:
            self.bets, self.last_raise, self.raises, self.actor = [0, 0], 0, 0, 1
        self.acted = [False, False]
        self.folder = None
        self.done = 0 in stacks              # someone is all-in: no more betting this hand

    def max_raise(self):
        a, o = self.actor, 1 - self.actor
        return min(self.bets[a] + self.stacks[a], self.bets[o] + self.stacks[o])

    def request(self):
        """The engine's action_request fields for the player to act."""
        a, o = self.actor, 1 - self.actor
        to_call = self.bets[o] - self.bets[a]
        max_raise = self.max_raise()
        legal = ["fold", "call"] if to_call > 0 else ["check"]
        can_raise = self.raises < MAX_RAISES and max_raise > self.bets[o]
        if can_raise:
            legal.append("raise")
        req = {"street": self.street, "pot": sum(self.committed),
               "my_bet": self.bets[a], "opp_bet": self.bets[o], "to_call": to_call,
               "my_stack": self.stacks[a], "opp_stack": self.stacks[o], "legal_actions": legal}
        if can_raise:
            req["min_raise"] = min(self.bets[o] + max(self.last_raise, 2), max_raise)
            req["max_raise"] = max_raise
        req["raises_left"] = MAX_RAISES - self.raises
        return req

    def apply(self, action, amount=None):
        """Apply a legal action; raises ValueError on an illegal one (state unchanged)."""
        if self.done:
            raise ValueError("street is over")
        req = self.request()
        if action not in req["legal_actions"]:
            raise ValueError(f"{action} not legal on {self.street}: {req['legal_actions']}")
        if action == "raise":
            if isinstance(amount, bool) or not isinstance(amount, int) \
                    or not req["min_raise"] <= amount <= req["max_raise"]:
                raise ValueError(f"raise amount {amount!r} outside [{req['min_raise']}, {req['max_raise']}]")
        a, o = self.actor, 1 - self.actor
        if action == "fold":
            self.folder = a
            self.done = True
            self._finish()
            return
        if action == "call":
            to_call = self.bets[o] - self.bets[a]
            self.stacks[a] -= to_call
            self.committed[a] += to_call
            self.bets[a] = self.bets[o]
        elif action == "raise":
            add = amount - self.bets[a]
            self.stacks[a] -= add
            self.committed[a] += add
            self.last_raise = amount - self.bets[o]
            self.bets[a] = amount
            self.raises += 1
            self.acted[o] = False
            if self.hand is not None:
                if self.street == "preflop":
                    self.hand.pagg = a + 1
                elif self.street == "flop":
                    self.hand.fagg = a + 1
        self.acted[a] = True
        if self.acted[0] and self.acted[1] and self.bets[0] == self.bets[1]:
            self.done = True
            self._finish()
            return
        self.actor = o

    def _finish(self):
        if self.hand is not None:
            self.hand.street_bets[self.street] = tuple(self.bets)
            if self.folder is not None:
                self.hand.folder = self.folder


class HandState:
    """Chip state across streets, plus the context features pot-at-street-start, pagg, fagg."""

    def __init__(self):
        self.stacks = [STARTING_STACK - SMALL_BLIND, STARTING_STACK - BIG_BLIND]
        self.committed = [SMALL_BLIND, BIG_BLIND]
        self.pot_start = {}
        self.street_bets = {}
        self.pagg = 0          # 0 none, 1 button, 2 big blind (last voluntary preflop raise)
        self.fagg = 0          # same for flop bets and raises
        self.folder = None
        self.cur = None

    def start_street(self, street):
        self.pot_start[street] = sum(self.committed)
        self.cur = StreetState(street, self.stacks, self.committed, self)
        if self.cur.done:
            self.street_bets[street] = (0, 0)
        return self.cur


# ---------------------------------------------------------------- history replay

Step = namedtuple("Step", "street node seat actor slot action amount req")


# Default raise translation for replay_history: a deterministic stand-in used by tools and tests.
# The bot passes its §9.4 translation (botsrc/translate.py) instead. A translate function is called as
# translate(node, opts, amount, max_raise, street=..., index=..., seat=..., req=...), where index is
# the entry's position in the history.
def nearest_translate(node, opts, amount, max_raise, **_):
    """Placeholder mapping of a raise to a slot (§9.4 translation arrives in Phase 6):
    all-in -> allin; anything else -> the size slot with the nearest amount (legal ones first).
    Never maps a non-all-in raise to allin, so the node keeps tracking the engine exactly."""
    if amount == max_raise and "allin" in node["slots"]:
        return "allin"
    cands = [(s, a) for s, ok, a in opts if ok and s in SIZE_SLOTS]
    if not cands:
        cands = [(s, a) for s, ok, a in opts if s in SIZE_SLOTS and a is not None]
    if not cands:
        return None
    return min(cands, key=lambda sa: abs(sa[1] - amount))[0]


class Replay:
    """Result of replay_history."""

    def __init__(self):
        self.steps = []
        self.committed = None
        self.stacks = None
        self.pot_start = {}
        self.street_bets = {}
        self.pagg = 0
        self.fagg = 0
        self.folder = None
        self.current_street = None
        self.current_node = None
        self.current_state = None
        self.lost = False          # an action could not be mapped to a slot
        self.error = None          # the history is inconsistent with the rules


class StreetReplay:
    """Walks one street's protocol history entries; yields Step(node, slot, amount, actor, ...)."""

    def __init__(self, hand, street, my_seat, translate):
        self.hand = hand
        self.street = street
        self.my_seat = my_seat
        self.translate = translate
        self.state = hand.start_street(street)
        self.tmpl = template_for(street)
        self.node = 0
        self.lost = False

    def step(self, entry, index=None):
        if not isinstance(entry, dict):
            raise ValueError(f"history entry is not an object: {entry!r}")
        if entry.get("street") != self.street:
            raise ValueError(f"{entry.get('street')!r} action while {self.street} betting is open")
        who = entry.get("actor")
        if who not in ("me", "opp"):
            raise ValueError(f"bad actor {who!r}")
        seat = self.my_seat if who == "me" else 1 - self.my_seat
        st = self.state
        if seat != st.actor:
            raise ValueError(f"seat {seat} acted, expected seat {st.actor}")
        req = st.request()
        action = entry.get("action")
        amount = entry.get("amount") if action == "raise" else None
        if action == "call" and entry.get("amount") is not None and entry["amount"] != req["opp_bet"]:
            raise ValueError(f"call to {entry['amount']}, expected {req['opp_bet']}")
        node, slot = self.node, None
        if node is not None and node >= 0:
            nd = self.tmpl[node]
            if action in ("fold", "check", "call"):
                slot = action if action in nd["slots"] else None
            elif action == "raise" and "raise" in req["legal_actions"] and isinstance(amount, int):
                slot = self.translate(nd, slot_options_req(self.street, nd, req), amount, req["max_raise"],
                                      street=self.street, index=index, seat=seat, req=req)
        st.apply(action, amount)                     # ValueError if illegal
        actor = None
        if node is not None and node >= 0:
            actor = self.tmpl[node]["actor"]
        if slot is None:
            self.lost = True
            self.node = None
        else:
            self.node = self.tmpl[node]["child"][slot]
        return Step(self.street, node, seat, actor, slot, action, amount, req)


def replay_history(history, my_seat, translate=None):
    """Replay a protocol `history` (all streets) from my_seat's view (0 button, 1 big blind).
    Never raises: inconsistencies set .error, unmappable actions set .lost."""
    translate = translate or nearest_translate
    rep = Replay()
    hand = HandState()
    i, n = 0, len(history)
    try:
        for street in STREETS:
            sr = StreetReplay(hand, street, my_seat, translate)
            rep.current_street = street
            while not sr.state.done and i < n:
                rep.steps.append(sr.step(history[i], i))
                i += 1
            rep.current_node = sr.node
            rep.current_state = sr.state
            rep.lost = rep.lost or sr.lost
            if not sr.state.done or sr.state.folder is not None:
                break
        if i < n:
            raise ValueError(f"{n - i} history entries left after the betting ended")
    except (ValueError, KeyError, TypeError, IndexError) as ex:
        rep.error = str(ex)
    rep.committed = list(hand.committed)
    rep.stacks = list(hand.stacks)
    rep.pot_start = dict(hand.pot_start)
    rep.street_bets = dict(hand.street_bets)
    rep.pagg, rep.fagg, rep.folder = hand.pagg, hand.fagg, hand.folder
    return rep
