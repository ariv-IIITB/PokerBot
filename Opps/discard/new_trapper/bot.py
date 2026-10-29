#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tight-passive "trapper" bot for Discard Hold'em (heads-up, 3 hole cards,
simultaneous exposed discard after the flop).  Run with:  python3.11 bot.py

Style
-----
* Few hands: folds the weak part of its range preflop and to aggression.
* Traps: slow-plays its strongest hands (check-calls, check-raises, checks
  behind in position) unless the board is wet, the opponent never bets
  (nothing to trap) or it is the river (then it takes its value).
* Calls down with medium-strength made hands when the price is right.
* Almost never bluffs (a ~3 % river stab when the opponent checks).

Engineering
-----------
* Only the standard library is used.  Nothing is read or written besides
  the protocol on stdin/stdout; stderr gets a few short error lines at most.
* Equity comes from a time-boxed Monte Carlo (pure-Python 7-card evaluator).
  The per-decision budget is derived from time_left_ms and the number of
  hands left, so the bank is never exhausted; with a nearly empty bank the
  bot switches to a cheap heuristic with no sampling.
* Three safety layers: every handler runs in try/except with a heuristic
  fallback, every reply is validated/clamped against legal_actions, and the
  main loop never lets an exception escape.
"""
import sys
import json
import time
import random
from bisect import bisect_right

_PERF = time.perf_counter

# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------
RANKS = "23456789TJQKA"
SUITS = "shdc"
C2I = {}
I2C = []
for _r in range(13):
    for _s in range(4):
        C2I[RANKS[_r] + SUITS[_s]] = _r * 4 + _s
        I2C.append(RANKS[_r] + SUITS[_s])


def parse_cards(lst):
    return [C2I[c] for c in lst]


# ---------------------------------------------------------------------------
# Hand evaluator (5..7 cards).  Card = rank*4 + suit.  Higher score = better.
# score = category << 20 | packed tie-break ranks (4 bits each)
# categories: 0 high card, 1 pair, 2 two pair, 3 trips, 4 straight, 5 flush,
#             6 full house, 7 quads, 8 straight flush
# ---------------------------------------------------------------------------
def _build_tables():
    straight = [-1] * 8192
    top5 = [0] * 8192
    for m in range(8192):
        for top in range(12, 2, -1):
            if top == 3:
                need = (1 << 12) | 0b1111          # A-2-3-4-5 (wheel)
            else:
                need = 0b11111 << (top - 4)
            if m & need == need:
                straight[m] = top
                break
        v = 0
        cnt = 0
        for r in range(12, -1, -1):
            if (m >> r) & 1:
                v = (v << 4) | r
                cnt += 1
                if cnt == 5:
                    break
        v <<= 4 * (5 - cnt)
        top5[m] = v
    return straight, top5


STRAIGHT, TOP5 = _build_tables()


def evaluate(cards):
    rc = [0] * 13
    sc = [0, 0, 0, 0]
    sm = [0, 0, 0, 0]
    for c in cards:
        r = c >> 2
        s = c & 3
        rc[r] += 1
        sc[s] += 1
        sm[s] |= 1 << r
    for s in range(4):
        if sc[s] >= 5:
            m = sm[s]
            st = STRAIGHT[m]
            if st >= 0:
                return (8 << 20) | (st << 16)
            return (5 << 20) | TOP5[m]
    quad = trip = p1 = p2 = -1
    mask = 0
    for r in range(12, -1, -1):
        n = rc[r]
        if n:
            mask |= 1 << r
            if n == 2:
                if p1 < 0:
                    p1 = r
                elif p2 < 0:
                    p2 = r
            elif n == 3:
                if trip < 0:
                    trip = r
                elif p1 < 0:
                    p1 = r
                elif p2 < 0:
                    p2 = r
            elif n == 4:
                quad = r
    if quad >= 0:
        km = mask & ~(1 << quad)
        return (7 << 20) | (quad << 16) | ((km.bit_length() - 1) << 12)
    if trip >= 0 and p1 >= 0:
        return (6 << 20) | (trip << 16) | (p1 << 12)
    st = STRAIGHT[mask]
    if st >= 0:
        return (4 << 20) | (st << 16)
    if trip >= 0:
        km = mask & ~(1 << trip)
        return (3 << 20) | (trip << 16) | ((TOP5[km] >> 4) & 0xFF00)
    if p2 >= 0:
        km = mask & ~((1 << p1) | (1 << p2))
        return (2 << 20) | (p1 << 16) | (p2 << 12) | ((km.bit_length() - 1) << 8)
    if p1 >= 0:
        km = mask & ~(1 << p1)
        return (1 << 20) | (p1 << 16) | ((TOP5[km] >> 4) & 0xFFF0)
    return TOP5[mask]


# ---------------------------------------------------------------------------
# Preflop strength (3 hole cards): Chen-style score of the best two-card
# subset plus a bonus for the flexibility of the third card, mapped to a
# percentile with a table obtained by sampling random three-card hands.
# ---------------------------------------------------------------------------
def _hv(r):
    if r == 12:
        return 10.0
    if r == 11:
        return 8.0
    if r == 10:
        return 7.0
    if r == 9:
        return 6.0
    return (r + 2) / 2.0


def _chen(r1, r2, suited):
    if r1 < r2:
        r1, r2 = r2, r1
    if r1 == r2:
        return max(5.0, _hv(r1) * 2.0)
    s = _hv(r1)
    if suited:
        s += 2.0
    gap = r1 - r2 - 1
    if gap == 1:
        s -= 1.0
    elif gap == 2:
        s -= 2.0
    elif gap == 3:
        s -= 4.0
    elif gap >= 4:
        s -= 5.0
    if gap <= 1 and r1 < 10:
        s += 1.0
    return s


def preflop_score(cards):
    a, b, c = cards
    ra, rb, rc_ = a >> 2, b >> 2, c >> 2
    if ra == rb == rc_:
        return 22.0 + ra * 0.2
    vals = [
        _chen(ra, rb, (a & 3) == (b & 3)),
        _chen(ra, rc_, (a & 3) == (c & 3)),
        _chen(rb, rc_, (b & 3) == (c & 3)),
    ]
    vals.sort(reverse=True)
    score = vals[0] + 0.30 * max(vals[1], 0.0)
    if (a & 3) == (b & 3) == (c & 3):
        score += 1.5
    return score


# Sorted preflop_score values at percentiles 1..100 of random 3-card hands.
PRE_Q = [
    2.0, 2.3, 2.5, 2.6, 2.8, 3.0, 3.25, 3.3, 3.6, 3.6, 3.75, 3.9, 3.9, 4.0,
    4.15, 4.3, 4.4, 4.5, 4.6, 4.75, 4.9, 4.9, 4.9, 5.0, 5.05, 5.15, 5.3,
    5.4, 5.5, 5.6, 5.6, 5.7, 5.75, 5.9, 5.9, 5.9, 6.05, 6.15, 6.2, 6.25,
    6.3, 6.4, 6.5, 6.5, 6.5, 6.5, 6.5, 6.6, 6.7, 6.85, 6.9, 6.9, 7.0, 7.2,
    7.3, 7.45, 7.5, 7.5, 7.6, 7.6, 7.8, 7.9, 7.9, 8.0, 8.2, 8.35, 8.5, 8.5,
    8.5, 8.5, 8.65, 8.8, 8.9, 8.9, 9.1, 9.3, 9.5, 9.5, 9.6, 9.8, 10.0, 10.1,
    10.4, 10.5, 10.6, 10.9, 11.1, 11.4, 11.5, 11.6, 12.1, 12.4, 12.7, 13.5,
    14.2, 15.0, 16.7, 17.8, 22.1, 24.4,
]


def preflop_pct(cards):
    s = preflop_score(cards)
    if PRE_Q:
        return bisect_right(PRE_Q, s) / float(len(PRE_Q))
    return max(0.0, min(1.0, s / 24.0))


# Calling thresholds (percentile needed) versus the amount to call preflop.
CALL_TABLE = [(1, 0.25), (2, 0.33), (4, 0.44), (6, 0.52), (8, 0.60),
              (12, 0.72), (16, 0.78), (30, 0.87), (60, 0.92),
              (100, 0.94), (200, 0.95)]


def call_threshold(to_call):
    t = CALL_TABLE
    if to_call <= t[0][0]:
        return t[0][1]
    for i in range(1, len(t)):
        x1, y1 = t[i]
        if to_call <= x1:
            x0, y0 = t[i - 1]
            return y0 + (y1 - y0) * (to_call - x0) / float(x1 - x0)
    return t[-1][1]


# ---------------------------------------------------------------------------
# Cheap heuristics
# ---------------------------------------------------------------------------
def heur_discard_idx(h, board):
    """Index (0..2) of the hole card that looks least useful on this flop."""
    brank = [c >> 2 for c in board]
    bsuit = [0, 0, 0, 0]
    for c in board:
        bsuit[c & 3] += 1
    best_i = 0
    best_v = 1e9
    for i in range(3):
        c = h[i]
        r = c >> 2
        s = c & 3
        v = float(r)
        if r in brank:
            v += 16.0
            if brank.count(r) > 1:
                v += 4.0
        for j in range(3):
            if j != i:
                o = h[j]
                orr = o >> 2
                if orr == r:
                    v += 9.0
                if (o & 3) == s and bsuit[s] >= 2:
                    v += 5.0
                d = orr - r
                if d < 0:
                    d = -d
                if 0 < d <= 2:
                    v += 1.2
        if bsuit[s] >= 3:
            v += 8.0
        elif bsuit[s] == 2:
            v += 2.0
        for br in brank:
            d = br - r
            if d < 0:
                d = -d
            if d == 1 or d == 2:
                v += 0.5
        if v < best_v:
            best_v = v
            best_i = i
    return best_i


def quick_eq(hole2, board):
    """Sampling-free strength estimate in [0,1] (emergency fallback)."""
    allc = list(hole2) + list(board)
    sc = evaluate(allc)
    cat = sc >> 20
    base = {0: 0.22, 1: 0.52, 2: 0.80, 3: 0.87, 4: 0.92, 5: 0.94,
            6: 0.97, 7: 0.99, 8: 0.995}[cat]
    bcat = evaluate(board) >> 20 if len(board) >= 3 else 0
    if cat <= bcat and cat <= 3:
        return 0.30 if cat <= 1 else base * 0.7
    if cat == 1:
        p = (sc >> 16) & 15
        bmax = max(c >> 2 for c in board) if board else 0
        base = 0.68 if p >= bmax else 0.48
    elif cat == 0:
        if max(c >> 2 for c in hole2) == 12:
            base += 0.04
    return base


def board_wetness(board):
    n = len(board)
    suits = [0, 0, 0, 0]
    for c in board:
        suits[c & 3] += 1
    w = 0.0
    ms = max(suits)
    if ms >= 3:
        w += 1.0
    elif ms == 2 and n < 5:
        w += 0.4
    ranks = sorted(set(c >> 2 for c in board))
    if 12 in ranks:
        ranks = [-1] + ranks
    best = 0
    for lo in range(len(ranks)):
        cnt = sum(1 for r in ranks if ranks[lo] <= r <= ranks[lo] + 4)
        if cnt > best:
            best = cnt
    if best >= 4:
        w += 1.0
    elif best == 3:
        w += 0.6
    return w


# ---------------------------------------------------------------------------
# Opponent model (simple counts with priors)
# ---------------------------------------------------------------------------
class OppModel:
    def __init__(self):
        self.pf_first = 0
        self.pf_first_raise = 0
        self.open_n = 0
        self.open_bet = 0
        self.vs_bet = 0
        self.vs_fold = 0
        self.vs_raise = 0

    def update(self, history):
        street = None
        bet_by = None
        pf_seen = False
        for e in history or []:
            if not isinstance(e, dict):
                continue
            st = e.get("street")
            who = e.get("actor")
            a = e.get("action")
            if st != street:
                street = st
                bet_by = None
            if st == "preflop":
                if who == "opp" and not pf_seen:
                    pf_seen = True
                    self.pf_first += 1
                    if a == "raise":
                        self.pf_first_raise += 1
                continue
            if who == "opp":
                if bet_by is None:
                    self.open_n += 1
                    if a == "raise":
                        self.open_bet += 1
                elif bet_by == "me":
                    self.vs_bet += 1
                    if a == "fold":
                        self.vs_fold += 1
                    elif a == "raise":
                        self.vs_raise += 1
                bet_by = "opp" if a == "raise" else None
            elif who == "me":
                bet_by = "me" if a == "raise" else None

    def open_bet_rate(self):
        return (self.open_bet + 1.5) / (self.open_n + 5.0)

    def fold_vs_bet(self):
        return (self.vs_fold + 1.5) / (self.vs_bet + 4.0)

    def pf_raise_rate(self):
        return (self.pf_first_raise + 1.5) / (self.pf_first + 5.0)


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


# ---------------------------------------------------------------------------
# The bot
# ---------------------------------------------------------------------------
class Bot:
    def __init__(self):
        self.rng = random.Random()
        self.total_hands = 400
        self.time_bank_ms = 60000
        self.time_left_ms = 60000
        self.hand_id = 0
        self.opp = OppModel()
        self.err_count = 0
        self._reset_hand()

    def _reset_hand(self):
        self.seat = None
        self.hole = []
        self.dead = []
        self.opp_disc = None
        self.pre_pct = 0.5
        self.flop_cache = None

    # -- logging ------------------------------------------------------------
    def log(self, text):
        if self.err_count < 25:
            self.err_count += 1
            try:
                sys.stderr.write(str(text)[:300] + "\n")
                sys.stderr.flush()
            except Exception:
                pass

    # -- time ---------------------------------------------------------------
    def note_time(self, msg):
        t = msg.get("time_left_ms")
        if isinstance(t, (int, float)):
            self.time_left_ms = t

    def budget(self, mult=1.0):
        tl = self.time_left_ms / 1000.0
        if tl < 2.5:
            return 0.0
        hands_left = max(20, self.total_hands - self.hand_id + 1)
        per_decision = tl / hands_left / 5.0
        b = per_decision * 0.40 * mult
        b = min(b, 0.30, tl * 0.12)
        if tl < 8.0:
            b = min(b, 0.004)
        return max(0.0, b)

    # -- message handlers ----------------------------------------------------
    def handle(self, msg):
        t = msg.get("type")
        if t == "init":
            self.on_init(msg)
        elif t == "new_hand":
            self.on_new_hand(msg)
        elif t == "action_request":
            return self.on_action_request(msg)
        elif t == "discard_request":
            return self.on_discard_request(msg)
        elif t == "discard_result":
            self.on_discard_result(msg)
        elif t == "hand_result":
            self.on_hand_result(msg)
        return None

    def on_init(self, msg):
        th = msg.get("total_hands")
        if isinstance(th, int) and th > 0:
            self.total_hands = th
        tb = msg.get("time_bank_ms")
        if isinstance(tb, (int, float)) and tb > 0:
            self.time_bank_ms = tb
            self.time_left_ms = tb

    def on_new_hand(self, msg):
        self._reset_hand()
        hid = msg.get("hand_id")
        if isinstance(hid, int):
            self.hand_id = hid
        else:
            self.hand_id += 1
        self.seat = msg.get("seat")
        try:
            self.hole = parse_cards(msg.get("hole_cards", []))
            if len(self.hole) == 3:
                self.pre_pct = preflop_pct(self.hole)
        except Exception as e:
            self.log("new_hand: %r" % (e,))
            self.hole = []

    def on_discard_result(self, msg):
        try:
            mine = msg.get("my_discard")
            theirs = msg.get("opp_discard")
            if mine in C2I:
                self.dead.append(C2I[mine])
            if theirs in C2I:
                self.opp_disc = C2I[theirs]
                self.dead.append(self.opp_disc)
            hc = msg.get("hole_cards")
            if isinstance(hc, list) and len(hc) == 2:
                self.hole = parse_cards(hc)
            elif len(self.hole) == 3 and mine in C2I:
                self.hole = [c for c in self.hole if c != C2I[mine]]
        except Exception as e:
            self.log("discard_result: %r" % (e,))

    def on_hand_result(self, msg):
        try:
            self.opp.update(msg.get("history"))
        except Exception as e:
            self.log("hand_result: %r" % (e,))

    # -- discard ---------------------------------------------------------------
    def on_discard_request(self, msg):
        self.note_time(msg)
        try:
            hole = parse_cards(msg["hole_cards"])
            if len(hole) != 3:
                raise ValueError("need 3 hole cards")
            self.hole = hole
            board = parse_cards(msg.get("board", []))
            idx = self.choose_discard(hole, board)
            return {"type": "discard", "card": I2C[hole[idx]]}
        except Exception as e:
            self.log("discard: %r" % (e,))
            return self.safe_discard(msg)

    def safe_discard(self, msg):
        try:
            cards = list(msg.get("hole_cards") or self.hole_strs())
            order = {"s": 0, "h": 1, "d": 2, "c": 3}
            worst = min(cards, key=lambda c: (RANKS.index(c[0]), order.get(c[1], 9)))
            return {"type": "discard", "card": worst}
        except Exception:
            return {"type": "discard", "card": "2s"}

    def hole_strs(self):
        return [I2C[c] for c in self.hole]

    def choose_discard(self, hole, board):
        """Index of the hole card to throw away."""
        if self.time_left_ms / 1000.0 < 2.5:
            return heur_discard_idx(hole, board)
        wins, n = self.mc_flop(hole, board, self.budget(2.0), 80, 900)
        if n <= 0:
            return heur_discard_idx(hole, board)
        best = 0
        for i in range(1, 3):
            if wins[i] > wins[best] + 1e-9:
                best = i
            elif abs(wins[i] - wins[best]) <= 1e-9 and (hole[i] >> 2) < (hole[best] >> 2):
                best = i
        return best

    # -- equity engines ----------------------------------------------------------
    def mc_flop(self, hole, flop, budget, min_n, max_n):
        """Equity of keeping each pair (index i = card thrown away) on the
        flop, against a random 3-card hand that discards by a heuristic.
        Samples are shared between candidates.  Returns (wins[3], n)."""
        key = (tuple(hole), tuple(flop))
        wins = [0.0, 0.0, 0.0]
        n = 0
        cache = self.flop_cache
        if cache is not None and cache[0] == key:
            wins = list(cache[1])
            n = cache[2]
        known = set(hole) | set(flop) | set(self.dead)
        unseen = [c for c in range(52) if c not in known]
        cands = [[hole[1], hole[2]], [hole[0], hole[2]], [hole[0], hole[1]]]
        rng = self.rng
        sample = rng.sample
        ev = evaluate
        t_end = _PERF() + budget
        flop_l = list(flop)
        done = 0
        while done < max_n and n < 3000:
            if done >= min_n and (done & 7) == 0 and _PERF() > t_end:
                break
            s = sample(unseen, 5)
            o3 = s[:3]
            di = heur_discard_idx(o3, flop_l)
            okeep = [o3[k] for k in range(3) if k != di]
            full = flop_l + s[3:5]
            op = ev(okeep + full)
            for i in range(3):
                me = ev(cands[i] + full)
                if me > op:
                    wins[i] += 1.0
                elif me == op:
                    wins[i] += 0.5
            done += 1
            n += 1
        self.flop_cache = (key, wins, n)
        if n <= 0:
            return wins, 0
        return [w / n for w in wins], n

    def mc_showdown(self, hole2, board, budget, min_n, max_n):
        """Equity of a 2-card hand against a random opponent hand with the
        remaining board cards dealt at random.  Dead cards (discards) are
        excluded; the opponent's known discard thins out hands that would
        have kept a clearly lower card than the one they threw away."""
        known = set(hole2) | set(board) | set(self.dead)
        unseen = [c for c in range(52) if c not in known]
        need = 5 - len(board)
        k = 2 + need
        rng = self.rng
        sample = rng.sample
        ev = evaluate
        dr = (self.opp_disc >> 2) if self.opp_disc is not None else None
        hole_l = list(hole2)
        board_l = list(board)
        fixed = None
        if need == 0:
            fixed = ev(hole_l + board_l)
        t_end = _PERF() + budget
        wins = 0.0
        n = 0
        while n < max_n:
            if n >= min_n and (n & 15) == 0 and _PERF() > t_end:
                break
            s = sample(unseen, k)
            o1 = s[0]
            o2 = s[1]
            if dr is not None:
                m = o1 >> 2
                m2 = o2 >> 2
                if m2 > m:
                    m = m2
                if dr > m and rng.random() < 0.5:
                    continue
            if need:
                full = board_l + s[2:]
                me = ev(hole_l + full)
            else:
                full = board_l
                me = fixed
            op = ev([o1, o2] + full)
            if me > op:
                wins += 1.0
            elif me == op:
                wins += 0.5
            n += 1
        if n == 0:
            return quick_eq(hole2, board)
        return wins / n

    def get_equity(self, board):
        """Equity estimate for the current decision."""
        emergency = self.time_left_ms / 1000.0 < 2.5
        if len(self.hole) == 3:                       # flop, before the discard
            if emergency:
                di = heur_discard_idx(self.hole, board)
                keep = [c for i, c in enumerate(self.hole) if i != di]
                return quick_eq(keep, board)
            wins, n = self.mc_flop(self.hole, board, self.budget(), 50, 500)
            if n <= 0:
                di = heur_discard_idx(self.hole, board)
                keep = [c for i, c in enumerate(self.hole) if i != di]
                return quick_eq(keep, board)
            return max(wins)
        if emergency:
            return quick_eq(self.hole, board)
        return self.mc_showdown(self.hole, board, self.budget(), 60, 1500)

    # -- action ----------------------------------------------------------------------
    def on_action_request(self, msg):
        self.note_time(msg)
        try:
            act, amt = self.decide(msg)
            return self.sanitize(act, amt, msg)
        except Exception as e:
            self.log("action: %r" % (e,))
            return self.safe_action(msg)

    def safe_action(self, msg):
        try:
            legal = msg.get("legal_actions") or []
            if "check" in legal:
                return {"type": "action", "action": "check"}
            to_call = msg.get("to_call") or 0
            pot = msg.get("pot") or 0
            if "call" in legal and to_call * 6 <= max(pot, 1):
                return {"type": "action", "action": "call"}
            if "fold" in legal:
                return {"type": "action", "action": "fold"}
            if "call" in legal:
                return {"type": "action", "action": "call"}
        except Exception:
            pass
        return {"type": "action", "action": "check"}

    def sanitize(self, act, amt, msg):
        legal = msg.get("legal_actions") or []
        if act == "raise":
            lo = msg.get("min_raise")
            hi = msg.get("max_raise")
            if "raise" in legal and isinstance(lo, int) and isinstance(hi, int):
                a = int(amt) if amt is not None else lo
                a = max(lo, min(hi, a))
                return {"type": "action", "action": "raise", "amount": a}
            act = "call" if "call" in legal else "check"
        if act == "fold" and "check" in legal:
            act = "check"
        if act == "check" and "check" not in legal:
            act = "call" if "call" in legal else "fold"
        if act == "call" and "call" not in legal:
            act = "check" if "check" in legal else "fold"
        if act not in legal:
            return self.safe_action(msg)
        return {"type": "action", "action": act}

    def size_to(self, msg, to_amount):
        """Clamp a raise-to amount; jam when it would commit most of the stack."""
        lo = msg["min_raise"]
        hi = msg["max_raise"]
        a = int(round(to_amount))
        if a >= 0.6 * hi:
            a = hi
        return max(lo, min(hi, a))

    def decide(self, msg):
        if len(self.hole) not in (2, 3):
            return self.fallback_decision(msg)
        if msg.get("street") == "preflop":
            return self.preflop(msg)
        return self.postflop(msg)

    def fallback_decision(self, msg):
        legal = msg.get("legal_actions") or []
        if "check" in legal:
            return "check", None
        return "fold", None

    # -- preflop -----------------------------------------------------------------------
    def preflop(self, msg):
        legal = msg.get("legal_actions") or []
        to_call = msg.get("to_call", 0)
        opp_bet = msg.get("opp_bet", 0)
        can_raise = "raise" in legal and "min_raise" in msg
        pct = self.pre_pct
        r = self.rng.random()
        hist = [h for h in (msg.get("history") or []) if h.get("street") == "preflop"]
        opp_raises = sum(1 for h in hist if h.get("actor") == "opp" and h.get("action") == "raise")

        if to_call <= 0:
            # Big blind, the opponent limped: raise only the very best hands
            # some of the time, otherwise trap by checking.
            if can_raise and pct >= 0.93 and r < 0.45:
                return "raise", self.size_to(msg, 8)
            return "check", None

        if opp_raises == 0 and opp_bet <= 2:
            # Small blind / button, first decision: complete or fold.
            if can_raise and pct >= 0.93 and r < 0.50:
                return "raise", self.size_to(msg, 6)
            if pct >= 0.42:
                return "call", None
            return "fold", None

        # Facing a raise.
        loosen = _clamp((self.opp.pf_raise_rate() - 0.35) * 0.35, -0.03, 0.08)
        thr = call_threshold(to_call) - loosen
        if can_raise and pct >= 0.965 and r < 0.55 and opp_bet < 0.5 * (msg.get("max_raise") or 200):
            return "raise", self.size_to(msg, opp_bet * 3)
        if pct >= thr:
            return "call", None
        return "fold", None

    # -- postflop --------------------------------------------------------------------------
    def postflop(self, msg):
        street = msg.get("street")
        board = parse_cards(msg.get("board", []))
        pot = msg.get("pot", 0)
        to_call = msg.get("to_call", 0)
        legal = msg.get("legal_actions") or []
        can_raise = "raise" in legal and "min_raise" in msg
        ip = (self.seat == "button")
        hist = [h for h in (msg.get("history") or []) if h.get("street") == street]
        my_checked = any(h.get("actor") == "me" and h.get("action") == "check" for h in hist)
        opp_raised_back = any(h.get("actor") == "opp" and h.get("action") == "raise" for h in hist) \
            and any(h.get("actor") == "me" and h.get("action") == "raise" for h in hist)
        eq = self.get_equity(board)
        rnd = self.rng.random
        agg = self.opp.open_bet_rate()
        wet = board_wetness(board)

        mon = 0.86 if street == "flop" else 0.88

        if to_call <= 0:
            # ----- we may check or bet -----
            if eq >= mon:
                if street == "river":
                    # take the money: a checking opponent will not bet for us
                    p_trap = 0.0 if ip else (0.55 if agg >= 0.30 else 0.15)
                    if can_raise and rnd() >= p_trap:
                        return "raise", self.size_to(msg, pot * (0.65 if ip else 0.75))
                    return "check", None
                p_slow = 0.70 if wet < 1.0 else 0.28
                p_slow *= _clamp(agg / 0.35, 0.35, 1.2)
                if eq >= 0.985 and wet < 1.0:
                    p_slow = min(0.95, p_slow + 0.15)
                if can_raise and rnd() >= p_slow:
                    return "raise", self.size_to(msg, pot * 0.55)
                return "check", None
            if eq >= 0.72:
                if street == "river":
                    p_bet = 0.65 if ip else 0.22
                    if can_raise and rnd() < p_bet:
                        return "raise", self.size_to(msg, pot * (0.5 if ip else 0.4))
                else:
                    p_bet = 0.25 if ip else 0.12
                    if can_raise and rnd() < p_bet:
                        return "raise", self.size_to(msg, pot * 0.4)
                return "check", None
            if street == "river" and ip and eq < 0.25 and can_raise and rnd() < 0.03 \
                    and self.opp.fold_vs_bet() >= 0.45:
                return "raise", self.size_to(msg, pot * 0.6)
            return "check", None

        # ----- facing a bet or raise -----
        pot_before = max(1, pot - to_call)
        ratio = to_call / float(pot_before)
        pot_odds = to_call / float(pot + to_call)
        base = {"flop": 0.07, "turn": 0.09, "river": 0.10}.get(street, 0.09)
        margin = base + 0.14 * min(1.3, ratio)
        if opp_raised_back:
            margin += 0.08
        if agg >= 0.55:
            margin -= 0.04
        elif agg <= 0.20:
            margin += 0.04
        req = pot_odds + margin

        if eq >= mon and can_raise:
            if street == "river":
                p_raise = 0.90
                frac = 0.9
            else:
                p_raise = 0.65 if my_checked else 0.35
                frac = 0.75
            if rnd() < p_raise:
                return "raise", self.size_to(msg, msg.get("opp_bet", 0) + frac * (pot + to_call))
            return "call", None
        if eq >= 0.78 and can_raise and street == "river" and rnd() < 0.12:
            return "raise", self.size_to(msg, msg.get("opp_bet", 0) + 0.7 * (pot + to_call))
        if eq >= req:
            return "call", None
        return "fold", None


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def _emit(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main():
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    bot = Bot()
    while True:
        try:
            line = sys.stdin.readline()
        except Exception:
            break
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if not isinstance(msg, dict):
            continue
        t = msg.get("type")
        if t == "match_end":
            break
        reply = None
        try:
            reply = bot.handle(msg)
        except Exception as e:
            bot.log("handle: %r" % (e,))
            try:
                if t == "action_request":
                    reply = bot.safe_action(msg)
                elif t == "discard_request":
                    reply = bot.safe_discard(msg)
            except Exception:
                reply = None
        if reply is not None:
            try:
                _emit(reply)
            except BrokenPipeError:
                break
            except Exception:
                break


if __name__ == "__main__":
    main()
