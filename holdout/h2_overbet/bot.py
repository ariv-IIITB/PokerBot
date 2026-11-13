"""h2_overbet: high-pressure aggressor for heads-up Discard Hold'em (JSON-lines protocol).

Style: opens wide, 3-bets light, bets most flops, overbets (1.0-2.0x pot) with a polarised
range (value + draws/blockers), fires multiple barrels, gives up on missed river hands, folds
marginal hands to raises but re-raises strong draws. Equity by Monte Carlo vs a random range.
Stdlib only. stdout = protocol only. Every decision path is wrapped; fallback is a legal action.
"""
import json
import random
import sys
import time

RANKS = "23456789TJQKA"
SUITS = "shdc"


def card_id(s):
    return RANKS.index(s[0]) * 4 + SUITS.index(s[1])


def card_str(c):
    return RANKS[c >> 2] + SUITS[c & 3]


# --------------------------------------------------------------------------- evaluator

def _straight_high(mask):
    """Highest straight top rank (3..12) in a 13-bit rank mask, or -1. Wheel = top 3."""
    m = (mask << 1) | ((mask >> 12) & 1)
    for t in range(12, 2, -1):
        if (m >> (t - 3)) & 31 == 31:
            return t
    return -1


def _pack(ranks):
    v = 0
    for r in ranks[:5]:
        v = (v << 4) | r
    for _ in range(5 - len(ranks[:5])):
        v <<= 4
    return v


def hand_value(cards):
    """Best 5-card value from 5..7 card ids. Larger is better (category << 20 | kickers)."""
    rc = [0] * 13
    sc = [0, 0, 0, 0]
    for c in cards:
        rc[c >> 2] += 1
        sc[c & 3] += 1
    mask = 0
    quads = []
    trips = []
    pairs = []
    singles = []
    for r in range(12, -1, -1):
        n = rc[r]
        if n:
            mask |= 1 << r
            if n == 4:
                quads.append(r)
            elif n == 3:
                trips.append(r)
            elif n == 2:
                pairs.append(r)
            else:
                singles.append(r)
    fs = -1
    for s in range(4):
        if sc[s] >= 5:
            fs = s
    if fs >= 0:
        fm = 0
        for c in cards:
            if (c & 3) == fs:
                fm |= 1 << (c >> 2)
        sh = _straight_high(fm)
        if sh >= 0:
            return (8 << 20) | sh
    if quads:
        q = quads[0]
        rest = [r for r in range(12, -1, -1) if rc[r] and r != q]
        return (7 << 20) | _pack([q] + rest[:1])
    if trips and (len(trips) > 1 or pairs):
        t = trips[0]
        p = max(trips[1:] + pairs)
        return (6 << 20) | _pack([t, p])
    if fs >= 0:
        rs = [r for r in range(12, -1, -1) if (fm >> r) & 1]
        return (5 << 20) | _pack(rs)
    sh = _straight_high(mask)
    if sh >= 0:
        return (4 << 20) | sh
    if trips:
        t = trips[0]
        rest = [r for r in range(12, -1, -1) if rc[r] and r != t]
        return (3 << 20) | _pack([t] + rest[:2])
    if len(pairs) >= 2:
        a, b = pairs[0], pairs[1]
        rest = [r for r in range(12, -1, -1) if rc[r] and r != a and r != b]
        return (2 << 20) | _pack([a, b] + rest[:1])
    if pairs:
        p = pairs[0]
        rest = [r for r in range(12, -1, -1) if rc[r] and r != p]
        return (1 << 20) | _pack([p] + rest[:3])
    return _pack(singles)


# --------------------------------------------------------------------------- equity (Monte Carlo)

FULL = list(range(52))


def mc_equity(hole, board, dead, n):
    """Equity of `hole` (2 cards) vs a random 2-card hand; random board completion."""
    used = set(hole) | set(board) | set(dead)
    deck = [c for c in FULL if c not in used]
    need = 5 - len(board)
    k = 2 + need
    win = 0.0
    for _ in range(n):
        s = random.sample(deck, k)
        full = board + s[2:]
        a = hand_value(hole + full)
        b = hand_value(s[:2] + full)
        if a > b:
            win += 1.0
        elif a == b:
            win += 0.5
    return win / n


def mc_equity3(hole3, board, n):
    """Equity with 3 cards (pre-discard): hindsight keep of best pair, both sides."""
    used = set(hole3) | set(board)
    deck = [c for c in FULL if c not in used]
    need = 5 - len(board)
    k = 3 + need
    keeps = [[hole3[0], hole3[1]], [hole3[0], hole3[2]], [hole3[1], hole3[2]]]
    win = 0.0
    for _ in range(n):
        s = random.sample(deck, k)
        full = board + s[3:]
        a = max(hand_value(p + full) for p in keeps)
        o = s[:3]
        b = max(hand_value([o[0], o[1]] + full), hand_value([o[0], o[2]] + full),
                hand_value([o[1], o[2]] + full))
        if a > b:
            win += 1.0
        elif a == b:
            win += 0.5
    return win / n


def best_discard(hole3, board, n):
    """Index of the card to discard, by equity of the kept pair (common random numbers)."""
    used = set(hole3) | set(board)
    deck = [c for c in FULL if c not in used]
    need = 5 - len(board)
    k = 2 + need
    keeps = [(hole3[1], hole3[2]), (hole3[0], hole3[2]), (hole3[0], hole3[1])]  # discard i
    tot = [0.0, 0.0, 0.0]
    for _ in range(n):
        s = random.sample(deck, k)
        full = board + s[2:]
        b = hand_value(s[:2] + full)
        for i in range(3):
            a = hand_value(list(keeps[i]) + full)
            tot[i] += 1.0 if a > b else (0.5 if a == b else 0.0)
    # tiny noise-free tie-break: prefer discarding the lowest rank
    return max(range(3), key=lambda i: (tot[i], -(hole3[i] >> 2)))


def draw_kind(hole, board):
    """(flush_draw, straight_outs_ranks) for a 2-card hole on a board with < 5 cards."""
    if len(board) >= 5:
        return False, 0
    cards = list(hole) + list(board)
    sc = [0, 0, 0, 0]
    for c in cards:
        sc[c & 3] += 1
    fd = False
    for s in range(4):
        if sc[s] == 4 and any((h & 3) == s for h in hole):
            fd = True
    mask = 0
    for c in cards:
        mask |= 1 << (c >> 2)
    base = _straight_high(mask)
    outs = 0
    if base < 0:
        for r in range(13):
            if not (mask >> r) & 1 and _straight_high(mask | (1 << r)) >= 0:
                outs += 1
    return fd, outs


# --------------------------------------------------------------------------- the bot

class Bot:
    def __init__(self):
        self.total_hands = 200
        self.bank_ms = 30000.0
        self.hand_id = 0
        self.hole = []
        self.board = []
        self.seat = "button"
        self.pre_eq = None
        self.pre_eq_hand = -1
        self.my_bets = 0       # raises of mine that got a response
        self.opp_folds = 0
        self.last_hist_len = 0
        self.opp_raises = 0
        self.opp_actions = 0
        self.flop_bet = False
        self.turn_bet = False
        self.hands_seen = 0

    # ---- bookkeeping
    def on_init(self, m):
        self.total_hands = int(m.get("total_hands", 200))
        self.bank_ms = float(m.get("time_bank_ms", 30000))

    def on_new_hand(self, m):
        self.hand_id = m.get("hand_id", 0)
        self.hole = [card_id(c) for c in m.get("hole_cards", [])]
        self.seat = m.get("seat", "button")
        self.board = []
        self.pre_eq = None
        self.flop_bet = False
        self.turn_bet = False
        self.hands_seen += 1

    def on_hand_result(self, m):
        hist = m.get("history", [])
        prev = None
        for e in hist:
            if prev is not None and prev.get("actor") == "me" and prev.get("action") == "raise" \
                    and e.get("actor") == "opp" and e.get("street") == prev.get("street"):
                self.my_bets += 1
                if e.get("action") == "fold":
                    self.opp_folds += 1
            if e.get("actor") == "opp":
                self.opp_actions += 1
                if e.get("action") == "raise":
                    self.opp_raises += 1
            prev = e

    def fold_rate(self):
        # prior 0.45 with weight 15
        return (self.opp_folds + 0.45 * 15) / (self.my_bets + 15)

    def samples(self, time_left_ms, base):
        hands_left = max(1, self.total_hands - self.hands_seen + 1)
        per_hand = time_left_ms / hands_left
        # ~5 decisions per hand; each sample ~ 25us*evals; keep mean well under 20 ms
        if per_hand < 25:
            return max(8, base // 8)
        if per_hand < 60:
            return max(16, base // 3)
        return base

    # ---- discard
    def discard(self, m):
        hole = [card_id(c) for c in m["hole_cards"]]
        board = [card_id(c) for c in m.get("board", [])]
        n = self.samples(float(m.get("time_left_ms", 30000)), 110)
        i = best_discard(hole, board, n)
        return {"type": "discard", "card": card_str(hole[i])}

    # ---- action
    def act(self, m):
        legal = m.get("legal_actions", [])
        street = m.get("street", "preflop")
        board = [card_id(c) for c in m.get("board", [])]
        self.board = board
        pot = int(m.get("pot", 0))
        my_bet = int(m.get("my_bet", 0))
        opp_bet = int(m.get("opp_bet", 0))
        to_call = int(m.get("to_call", 0))
        my_stack = int(m.get("my_stack", 0))
        raises_left = int(m.get("raises_left", 0))
        min_r = int(m.get("min_raise", 0)) if "raise" in legal else 0
        max_r = int(m.get("max_raise", 0)) if "raise" in legal else 0
        tl = float(m.get("time_left_ms", 30000))
        hole = self.hole
        if street == "preflop":
            return self.act_pre(legal, pot, my_bet, opp_bet, to_call, raises_left, min_r, max_r, tl)
        return self.act_post(legal, street, board, pot, my_bet, opp_bet, to_call, my_stack,
                             raises_left, min_r, max_r, tl, m.get("history", []))

    # helpers
    @staticmethod
    def clamp_raise(amount, min_r, max_r):
        a = int(round(amount))
        return max(min_r, min(max_r, a))

    def fold_or_check(self, legal):
        return ("check", None) if "check" in legal else ("fold", None)

    def call_or_check(self, legal):
        if "check" in legal:
            return ("check", None)
        if "call" in legal:
            return ("call", None)
        return ("fold", None)

    def act_pre(self, legal, pot, my_bet, opp_bet, to_call, raises_left, min_r, max_r, tl):
        if self.pre_eq is None:
            n = self.samples(tl, 90)
            self.pre_eq = mc_equity3(self.hole, [], n)
        e = self.pre_eq
        can_raise = "raise" in legal and raises_left > 0
        nraise = 4 - raises_left      # raises used so far (BB counts as 1)
        ranks = sorted((c >> 2) for c in self.hole)
        has_ace_king = ranks[-1] >= 11
        suits = [c & 3 for c in self.hole]
        suited = len(set(suits)) < 3
        light = (has_ace_king and suited)
        r = random.random()
        fr = self.fold_rate()
        if nraise <= 1:
            # open (button) or option (BB, opp limped)
            if can_raise and (e >= 0.465 or (e >= 0.42 and r < 0.55) or r < 0.12):
                size = random.choice((5, 6, 6, 7)) if "call" in legal else random.choice((5, 6, 6))
                return ("raise", self.clamp_raise(size, min_r, max_r))
            if "check" in legal:
                return ("check", None)
            return ("call", None) if e >= 0.42 else ("fold", None)
        if nraise == 2:
            # facing an open: 3-bet light in the big blind
            odds = to_call / float(pot + to_call)
            big = opp_bet >= 12
            if can_raise and not big:
                if e >= 0.585 or (e >= 0.53 and r < 0.40) or (light and r < 0.45) or r < 0.10 * fr / 0.45:
                    to = max(opp_bet * 3 + 1, min_r) if random.random() < 0.6 else opp_bet * 4
                    return ("raise", self.clamp_raise(to, min_r, max_r))
            if e >= odds + 0.10 or (e >= odds + 0.04 and not big):
                return ("call", None)
            return ("fold", None)
        if nraise == 3:
            # facing a 3-bet
            odds = to_call / float(pot + to_call)
            if can_raise and (e >= 0.645 or (e >= 0.60 and r < 0.30)):
                return ("raise", self.clamp_raise(opp_bet * 2.3, min_r, max_r))
            if e >= odds + 0.12:
                return ("call", None)
            return ("fold", None)
        # facing a 4-bet: continue only with strong hands
        if e >= 0.68 and "raise" in legal:
            return ("raise", max_r)
        if e >= 0.60:
            return ("call", None)
        return ("fold", None)

    def act_post(self, legal, street, board, pot, my_bet, opp_bet, to_call, my_stack,
                 raises_left, min_r, max_r, tl, history):
        sidx = {"flop": 0, "turn": 1, "river": 2}.get(street, 0)
        # equity + draw info
        if street == "flop" and len(self.hole) == 3:
            n = self.samples(tl, 80)
            e = mc_equity3(self.hole, board, n)
            fd = False
            outs = 0
            for i in range(3):
                kp = [c for j, c in enumerate(self.hole) if j != i]
                f, o = draw_kind(kp, board)
                fd = fd or f
                outs = max(outs, o)
            holep = self.hole
        else:
            holep = self.hole[:2] if len(self.hole) > 2 else self.hole
            dead = getattr(self, "dead", [])
            n = self.samples(tl, 140)
            e = mc_equity(holep, board, dead, n)
            fd, outs = draw_kind(holep, board)
        draw = (street != "river") and (fd or outs >= 2)
        strong_draw = (street != "river") and (fd or outs >= 2) and e >= 0.30
        # blocker on the river: ace of a flush suit on board or top-card blocker
        blocker = False
        if street == "river" and holep:
            bs = [0, 0, 0, 0]
            for c in board:
                bs[c & 3] += 1
            for h in holep:
                if bs[h & 3] >= 3 and (h >> 2) >= 10:
                    blocker = True
            if max(c >> 2 for c in holep) == 12 and max(c >> 2 for c in board) < 12:
                blocker = True
        fr = self.fold_rate()
        bluff_scale = min(1.5, max(0.5, fr / 0.45))
        r = random.random()
        can_raise = "raise" in legal and raises_left > 0 and max_r > 0
        eff = my_stack  # chips behind (opponent's stack is equal-ish)

        def bet(frac):
            tot = pot + to_call
            to = opp_bet + frac * tot if to_call else my_bet + frac * pot
            if to_call == 0:
                to = frac * pot
            a = self.clamp_raise(to, min_r, max_r)
            # commit most of the stack -> shove
            if a >= 0.55 * (my_stack + my_bet):
                a = max_r
            return ("raise", a)

        if to_call == 0:
            # ----- we act with no bet to face
            if not can_raise:
                return ("check", None)
            if sidx == 0:
                if e >= 0.72:
                    p = 0.95
                    f = random.choice((1.0, 1.25, 1.5, 2.0))
                elif e >= 0.52:
                    p = 0.80
                    f = random.choice((0.75, 1.0, 1.0, 1.5))
                elif strong_draw:
                    p = 0.88 * bluff_scale
                    f = random.choice((1.0, 1.5, 2.0))
                else:
                    p = 0.50 * bluff_scale
                    f = random.choice((0.7, 1.0, 1.0))
                if random.random() < min(p, 0.97):
                    self.flop_bet = True
                    return bet(f)
                return ("check", None)
            if sidx == 1:
                if e >= 0.72:
                    p, f = 0.92, random.choice((1.0, 1.5, 2.0))
                elif e >= 0.55:
                    p, f = 0.60, random.choice((0.7, 1.0))
                elif strong_draw:
                    p, f = 0.75 * bluff_scale, random.choice((1.0, 1.5, 2.0))
                else:
                    p, f = (0.42 if self.flop_bet else 0.18) * bluff_scale, random.choice((1.0, 1.5))
                if random.random() < min(p, 0.97):
                    self.turn_bet = True
                    return bet(f)
                return ("check", None)
            # river
            if e >= 0.74:
                p, f = 0.92, random.choice((1.0, 1.5, 2.0))
            elif e >= 0.60:
                p, f = 0.45, random.choice((0.5, 0.75))
            elif e < 0.40 and blocker and self.turn_bet:
                p, f = 0.30 * bluff_scale, random.choice((1.0, 1.5, 2.0))
            elif e < 0.40 and blocker:
                p, f = 0.12 * bluff_scale, 1.0
            else:
                p, f = 0.0, 0.0
            if random.random() < p:
                return bet(f)
            return ("check", None)

        # ----- facing a bet or raise
        facing_reraise = my_bet > 0
        pot_before = max(1, pot - to_call)
        odds = to_call / float(pot + to_call)
        # opponent bet range is stronger than random: shrink equity with bet size
        e_adj = e - 0.10 * min(1.5, to_call / float(pot_before))
        if facing_reraise:
            e_adj -= 0.04
        if can_raise and e >= 0.80 and r < 0.70:
            return bet(random.choice((0.8, 1.0, 1.0)))
        if can_raise and strong_draw and street != "river" and r < 0.55 * bluff_scale \
                and to_call < 0.45 * (my_stack + my_bet):
            return bet(random.choice((0.8, 1.0)))
        # bluff-raise (3-bet bluff) rarely with blockers on river
        if can_raise and street == "river" and blocker and e < 0.40 and r < 0.06:
            return bet(1.0)
        margin = 0.04 if not facing_reraise else 0.12
        if e_adj >= odds + margin:
            return ("call", None)
        if strong_draw and street == "flop" and e >= odds - 0.02 and to_call <= 0.4 * pot_before:
            return ("call", None)
        return ("fold", None)

    # ---- dispatch
    def decide(self, m):
        t = m.get("type")
        if t == "action_request":
            kind, amt = self.act(m)
            legal = m.get("legal_actions", [])
            return self.validate(kind, amt, m, legal)
        if t == "discard_request":
            return self.discard(m)
        return None

    def validate(self, kind, amt, m, legal):
        if kind == "raise" and "raise" in legal:
            lo, hi = int(m["min_raise"]), int(m["max_raise"])
            a = max(lo, min(hi, int(amt if amt is not None else lo)))
            return {"type": "action", "action": "raise", "amount": a}
        if kind in legal and kind != "raise":
            return {"type": "action", "action": kind}
        return self.safe(m)

    def safe(self, m):
        legal = m.get("legal_actions", [])
        if "check" in legal:
            return {"type": "action", "action": "check"}
        if "call" in legal:
            return {"type": "action", "action": "call"}
        return {"type": "action", "action": "fold"}

    def handle(self, m):
        t = m.get("type")
        if t == "init":
            self.on_init(m)
        elif t == "new_hand":
            self.on_new_hand(m)
            self.dead = []
        elif t == "discard_result":
            self.hole = [card_id(c) for c in m.get("hole_cards", [])]
            self.dead = []
            for k in ("my_discard", "opp_discard"):
                try:
                    self.dead.append(card_id(m[k]))
                except Exception:
                    pass
        elif t == "hand_result":
            self.on_hand_result(m)
        elif t in ("action_request", "discard_request"):
            try:
                return self.decide(m)
            except Exception as ex:  # never crash
                print("WARN decide failed: %r" % (ex,), file=sys.stderr)
                if t == "discard_request":
                    return self.safe_discard(m)
                return self.safe(m)
        return None

    @staticmethod
    def safe_discard(m):
        cards = m.get("hole_cards", [])
        try:
            worst = min(cards, key=lambda c: RANKS.index(c[0]))
        except Exception:
            worst = cards[0] if cards else "2c"
        return {"type": "discard", "card": worst}


def main():
    bot = Bot()
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if not isinstance(m, dict):
            continue
        if m.get("type") == "match_end":
            break
        try:
            reply = bot.handle(m)
        except Exception as ex:
            print("WARN handle failed: %r" % (ex,), file=sys.stderr)
            t = m.get("type")
            reply = bot.safe(m) if t == "action_request" else (
                Bot.safe_discard(m) if t == "discard_request" else None)
        if reply is not None:
            out.write(json.dumps(reply) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
