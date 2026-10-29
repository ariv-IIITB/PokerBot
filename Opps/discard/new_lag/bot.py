#!/usr/bin/env python3
"""Loose-aggressive Discard Hold'em bot (Python 3.11, standard library only).

Run:  python3.11 bot.py        (speaks the JSON-lines protocol on stdin/stdout)

Style
  * Preflop: opens or raises ~90% of hands from the button, defends the big blind
    wide, 3-bets and 4-bets light (random mixing, ace blockers favoured).
  * Postflop: bets most flops, keeps firing on turn and river, bluffs a lot with
    random mixing, bets 60-100% of the pot, and folds to heavy resistance only
    with its weakest hands.
Engine room
  * Fast pure-Python 5-7 card evaluator (table driven).
  * Monte-Carlo equity with a time-boxed loop. The opponent range is weighted by
    its betting pressure and by what it discarded.
  * The discard is chosen by the same simulation (best of the three 2-card keeps).
  * Light opponent modelling (fold-to-bet, bet frequency, preflop open rate).
Safety
  * Every decision is wrapped: any exception falls back to a legal, simple action.
  * Every reply is validated against legal_actions / min_raise / max_raise.
  * Time use is paced from time_left_ms and the number of hands left.
  * stdout carries protocol lines only; nothing is read or written besides stdin/stdout.
"""
import sys
import json
import random
import time
from bisect import bisect_left, bisect_right
from itertools import combinations

# --------------------------------------------------------------------------
# Cards: id = rank*4 + suit, rank 0..12 ('2'..'A'), suit 0..3 ('s','h','d','c')
# --------------------------------------------------------------------------
RANKS = "23456789TJQKA"
SUITS = "shdc"
CARD_ID = {RANKS[r] + SUITS[s]: r * 4 + s for r in range(13) for s in range(4)}
CARD_STR = [RANKS[c >> 2] + SUITS[c & 3] for c in range(52)]


def parse_cards(lst):
    return [CARD_ID[c] for c in lst]


# --------------------------------------------------------------------------
# Hand evaluator. Score = category << 20 | up to five 4-bit rank nibbles.
# categories: 0 high card, 1 pair, 2 two pair, 3 trips, 4 straight, 5 flush,
#             6 full house, 7 quads, 8 straight flush
# --------------------------------------------------------------------------
def _build_tables():
    straight = [-1] * 8192
    top5 = [0] * 8192
    for m in range(8192):
        st = -1
        for t in range(12, 3, -1):
            w = 31 << (t - 4)
            if m & w == w:
                st = t
                break
        if st < 0 and (m & 0x100F) == 0x100F:  # A2345 (wheel), top card is the 5
            st = 3
        straight[m] = st
        v = 0
        n = 0
        for r in range(12, -1, -1):
            if (m >> r) & 1:
                v |= r << (16 - 4 * n)
                n += 1
                if n == 5:
                    break
        top5[m] = v
    return straight, top5


STRAIGHT, TOP5 = _build_tables()


def evaluate(cards, _ST=STRAIGHT, _T5=TOP5):
    """Best 5-card hand score from 5..7 card ids (works with fewer, too)."""
    rc = [0] * 13
    sc = [0, 0, 0, 0]
    sm = [0, 0, 0, 0]
    mask = 0
    for c in cards:
        r = c >> 2
        s = c & 3
        b = 1 << r
        rc[r] += 1
        sc[s] += 1
        sm[s] |= b
        mask |= b
    if sc[0] >= 5 or sc[1] >= 5 or sc[2] >= 5 or sc[3] >= 5:
        for s in range(4):
            if sc[s] >= 5:
                m = sm[s]
                st = _ST[m]
                if st >= 0:
                    return 0x800000 | (st << 16)
                return 0x500000 | _T5[m]
    quad = -1
    t1 = -1
    t2 = -1
    p1 = -1
    p2 = -1
    for r in range(12, -1, -1):
        n = rc[r]
        if n >= 2:
            if n == 4:
                if quad < 0:
                    quad = r
            elif n == 3:
                if t1 < 0:
                    t1 = r
                elif t2 < 0:
                    t2 = r
            else:
                if p1 < 0:
                    p1 = r
                elif p2 < 0:
                    p2 = r
    if quad >= 0:
        return 0x700000 | (quad << 16) | ((_T5[mask & ~(1 << quad)] >> 16) << 12)
    if t1 >= 0:
        if t2 >= 0 or p1 >= 0:
            second = t2 if t2 > p1 else p1
            return 0x600000 | (t1 << 16) | (second << 12)
    st = _ST[mask]
    if st >= 0:
        return 0x400000 | (st << 16)
    if t1 >= 0:
        return 0x300000 | (t1 << 16) | ((_T5[mask & ~(1 << t1)] & 0xFF000) >> 4)
    if p2 >= 0:
        rest = mask & ~(1 << p1) & ~(1 << p2)
        return 0x200000 | (p1 << 16) | (p2 << 12) | ((_T5[rest] >> 16) << 8)
    if p1 >= 0:
        return 0x100000 | (p1 << 16) | ((_T5[mask & ~(1 << p1)] & 0xFFF00) >> 4)
    return _T5[mask]


def draw_level(h0, h1, board, _ST=STRAIGHT):
    """0 = no draw, 1 = gutshot, 2 = flush draw or open-ended straight draw."""
    sc = [0, 0, 0, 0]
    hs = [0, 0, 0, 0]
    bm = 0
    for c in board:
        sc[c & 3] += 1
        bm |= 1 << (c >> 2)
    mask = bm
    for c in (h0, h1):
        sc[c & 3] += 1
        hs[c & 3] += 1
        mask |= 1 << (c >> 2)
    for s in range(4):
        if sc[s] == 4 and hs[s] >= 1:
            return 2
    if _ST[mask] >= 0:
        return 0
    n = 0
    for r in range(13):
        if not (mask >> r) & 1:
            if _ST[mask | (1 << r)] >= 0 and _ST[bm | (1 << r)] < 0:
                n += 1
    return 2 if n >= 2 else n


DRAW2 = 0x100000 | (9 << 16)  # a strong draw is treated as at least a pair of jacks
DRAW1 = 0x100000 | (6 << 16)  # a gutshot as at least a pair of eights


def strength(a, b, board):
    """Current-board strength of a 2-card hand, with a floor for draws."""
    sc = evaluate([a, b] + board)
    if sc < DRAW2 and len(board) < 5:
        d = draw_level(a, b, board)
        if d == 2:
            return DRAW2
        if d == 1 and sc < DRAW1:
            return DRAW1
    return sc


def quick_eq(hole, board):
    """Cheap one-evaluation equity guess (fallback when there is no time for MC)."""
    sc = evaluate(list(hole) + list(board))
    cat = sc >> 20
    bcat = evaluate(list(board)) >> 20
    if cat > bcat:
        if cat == 1:
            pr = (sc >> 16) & 15
            br = max(c >> 2 for c in board)
            if pr > br:
                eq = 0.66 if (hole[0] >> 2) == (hole[1] >> 2) else 0.58
            elif pr == br:
                eq = 0.55
            else:
                eq = 0.38
        else:
            eq = {2: 0.76, 3: 0.86, 4: 0.90, 5: 0.92, 6: 0.95, 7: 0.98, 8: 0.99}.get(cat, 0.9)
    else:
        eq = 0.17 + 0.012 * max(hole[0] >> 2, hole[1] >> 2)
    if len(board) < 5 and eq < 0.6:
        eq += (0.0, 0.05, 0.16)[draw_level(hole[0], hole[1], list(board))]
    return min(0.99, eq)


# --------------------------------------------------------------------------
# Preflop hand strength for 3 hole cards: Chen-style score of the best pair of
# the three, plus flexibility bonuses, converted to a percentile over all hands.
# --------------------------------------------------------------------------
def _pts(r):
    if r == 12:
        return 10.0
    if r == 11:
        return 8.0
    if r == 10:
        return 7.0
    if r == 9:
        return 6.0
    return (r + 2) / 2.0


_GAP = (0, 1, 2, 4, 5)


def chen2(r1, r2, suited):
    hi = r1 if r1 > r2 else r2
    lo = r2 if r1 > r2 else r1
    if hi == lo:
        v = 2 * _pts(hi)
        return v if v > 5 else 5.0
    v = _pts(hi)
    gap = hi - lo - 1
    v -= _GAP[gap if gap < 4 else 4]
    if gap <= 1 and hi < 10:
        v += 1.0
    if suited:
        v += 2.0
    return v


def pf_score(cs):
    rs = [c >> 2 for c in cs]
    ss = [c & 3 for c in cs]
    sc = [chen2(rs[0], rs[1], ss[0] == ss[1]),
          chen2(rs[0], rs[2], ss[0] == ss[2]),
          chen2(rs[1], rs[2], ss[1] == ss[2])]
    sc.sort(reverse=True)
    v = sc[0] + 0.25 * sc[1] + 0.05 * sc[2]
    if ss[0] == ss[1] == ss[2]:
        v += 1.0
    srt = sorted(rs)
    if srt[0] == srt[2]:
        v += 3.0
    elif srt[0] != srt[1] and srt[1] != srt[2] and srt[2] - srt[0] <= 4:
        v += 1.0
    return v


PF_SORTED = sorted(pf_score(c) for c in combinations(range(52), 3))
_PF_N = float(len(PF_SORTED))
_PF_CACHE = {}


def pf_pct(cards):
    key = tuple(sorted(cards))
    v = _PF_CACHE.get(key)
    if v is None:
        s = pf_score(key)
        v = (bisect_left(PF_SORTED, s) + bisect_right(PF_SORTED, s)) / (2.0 * _PF_N)
        _PF_CACHE[key] = v
    return v


# --------------------------------------------------------------------------
# Monte-Carlo sample sets
# --------------------------------------------------------------------------
class SampleSet(object):
    """Opponent-hand / runout samples with per-hero-option outcomes."""
    __slots__ = ("ostr", "wd", "res", "pct", "nopt", "n")

    def __init__(self, nopt):
        self.ostr = []
        self.wd = []
        self.res = []
        self.pct = None
        self.nopt = nopt
        self.n = 0

    def _compute_pct(self):
        n = len(self.ostr)
        ostr = self.ostr
        order = sorted(range(n), key=ostr.__getitem__)
        pct = [0.5] * n
        i = 0
        while i < n:
            j = i
            v = ostr[order[i]]
            while j + 1 < n and ostr[order[j + 1]] == v:
                j += 1
            p = ((i + j) / 2.0) / (n - 1) if n > 1 else 0.5
            for t in range(i, j + 1):
                pct[order[t]] = p
            i = j + 1
        self.pct = pct

    def equities(self, k):
        """Weighted equity per hero option; k = opponent range tightness exponent."""
        n = len(self.ostr)
        nopt = self.nopt
        if n == 0:
            return [0.5] * nopt
        if self.pct is None:
            self._compute_pct()
        pct = self.pct
        wd = self.wd
        res = self.res
        acc = [0.0] * nopt
        tw = 0.0
        tight = k > 0.02
        for i in range(n):
            w = wd[i]
            if tight:
                w *= 0.15 + 0.85 * (pct[i] ** k)
            tw += w
            r = res[i]
            for j in range(nopt):
                acc[j] += w * r[j]
        if tw <= 0.0:
            return [0.5] * nopt
        return [a / tw for a in acc]


def clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


STREET_IDX = {"preflop": 0, "flop": 0, "turn": 1, "river": 2}
CHECK = {"type": "action", "action": "check"}
CALL = {"type": "action", "action": "call"}
FOLD = {"type": "action", "action": "fold"}


def lowest_card(cards):
    """Engine's default discard: lowest rank, ties by suit order s,h,d,c."""
    return min(cards, key=lambda c: (c >> 2, c & 3))


class Bot(object):
    def __init__(self):
        self.rng = random.Random(time.time_ns() ^ 0x5DEECE66D)
        self.total_hands = 400
        self.time_bank_ms = 60000
        self.hand_id = 0
        self.seat = "button"
        self.hole = []
        self.dead = []
        self.my_discard = None
        self.opp_discard = None
        self.flop = None
        self.fkc = {}
        self.sets = {}
        self.k_flop = 0.0
        self.errors = 0
        self.st = {
            "post_face_n": 0, "post_face_fold": 0, "post_face_raise": 0,
            "post_free_n": 0, "post_free_bet": 0,
            "pf_open_n": 0, "pf_open_raise": 0,
        }

    # ------------------------------------------------------------------ stats
    def _rate(self, num, den, prior, strength_=10.0):
        return (num + prior * strength_) / (den + strength_)

    def bluff_mult(self):
        s = self.st
        fr = self._rate(s["post_face_fold"], s["post_face_n"], 0.40)
        return clamp(1.0 + 1.6 * (fr - 0.40), 0.55, 1.5)

    def k_mult(self):
        s = self.st
        br = self._rate(s["post_free_bet"], s["post_free_n"], 0.40)
        return clamp(1.0 - 1.2 * (br - 0.40), 0.6, 1.3)

    def call_mult(self):
        s = self.st
        br = self._rate(s["post_free_bet"], s["post_free_n"], 0.40)
        return clamp(1.0 - 0.7 * (br - 0.40), 0.85, 1.12)

    def defend_mult(self):
        s = self.st
        orr = self._rate(s["pf_open_raise"], s["pf_open_n"], 0.65)
        return clamp(1.0 - 0.8 * (orr - 0.65), 0.75, 1.2)

    def update_stats(self, hist):
        st = self.st
        if self.seat == "button":
            commit = {"me": 1, "opp": 2}
        else:
            commit = {"me": 2, "opp": 1}
        cur = "preflop"
        nraise = 1
        last_raiser = None
        for idx, e in enumerate(hist):
            street = e.get("street")
            actor = e.get("actor")
            act = e.get("action")
            amt = e.get("amount")
            if street != cur:
                cur = street
                commit = {"me": 0, "opp": 0}
                nraise = 0
                last_raiser = None
            if actor not in ("me", "opp"):
                continue
            other = "opp" if actor == "me" else "me"
            facing = commit[other] > commit[actor]
            if actor == "opp":
                if street == "preflop":
                    if idx == 0 and self.seat == "big_blind":
                        st["pf_open_n"] += 1
                        if act == "raise":
                            st["pf_open_raise"] += 1
                else:
                    if facing:
                        st["post_face_n"] += 1
                        if act == "fold":
                            st["post_face_fold"] += 1
                        elif act == "raise":
                            st["post_face_raise"] += 1
                    else:
                        st["post_free_n"] += 1
                        if act == "raise":
                            st["post_free_bet"] += 1
            if act == "fold":
                break
            if act in ("call", "raise") and isinstance(amt, int):
                commit[actor] = amt
            if act == "raise":
                nraise += 1
                last_raiser = actor

    # ---------------------------------------------------------------- pacing
    def mc_budget(self, tl_ms, kind):
        hands_left = max(10, self.total_hands - self.hand_id + 1)
        pace = (tl_ms / 1000.0) / hands_left
        share = {"flop": 0.45, "turn": 0.27, "river": 0.22}.get(kind, 0.2)
        return min(0.20, 0.40 * pace * share)

    # ------------------------------------------------------------- sampling
    def flopkey(self, a, b):
        if a > b:
            a, b = b, a
        kk = (a << 6) | b
        v = self.fkc.get(kk)
        if v is None:
            s = strength(a, b, self.flop)
            v = (s << 5) | ((a >> 2) + (b >> 2))
            self.fkc[kk] = v
        return v

    def build(self, hero_opts, board, opp_n, n_max, tbudget):
        now = time.perf_counter
        t_end = now() + tbudget
        if self.flop is None:
            self.flop = list(board[:3])
            self.fkc = {}
        known = set(board)
        known.update(self.dead)
        for o in hero_opts:
            known.update(o)
        pool = [c for c in range(52) if c not in known]
        nb = len(board)
        need = opp_n + 5 - nb
        sample = self.rng.sample
        fk = self.flopkey
        oppd = self.opp_discard if opp_n == 2 else None
        ss = SampleSet(len(hero_opts))
        ostr_l = ss.ostr
        wd_l = ss.wd
        res_l = ss.res
        board = list(board)
        i = 0
        while i < n_max:
            if i >= 12 and (i & 7) == 0 and now() > t_end:
                break
            cs = sample(pool, need)
            i += 1
            ostr = None
            w = 1.0
            if opp_n == 3:
                a, b, c = cs[0], cs[1], cs[2]
                k1 = fk(a, b)
                k2 = fk(a, c)
                k3 = fk(b, c)
                if k1 >= k2 and k1 >= k3:
                    o0, o1, kb = a, b, k1
                elif k2 >= k3:
                    o0, o1, kb = a, c, k2
                else:
                    o0, o1, kb = b, c, k3
                ostr = kb >> 5
                run = cs[3:]
            else:
                o0, o1 = cs[0], cs[1]
                run = cs[2:]
                if oppd is not None:
                    k1 = fk(o0, o1)
                    if k1 < fk(o0, oppd) or k1 < fk(o1, oppd):
                        w = 0.4
            fb = board + run
            oscore = evaluate([o0, o1] + fb)
            if ostr is None:
                ostr = oscore if nb == 5 else strength(o0, o1, board)
            r = []
            for opt in hero_opts:
                hs = evaluate([opt[0], opt[1]] + fb)
                r.append(1.0 if hs > oscore else (0.5 if hs == oscore else 0.0))
            ostr_l.append(ostr)
            wd_l.append(w)
            res_l.append(r)
        ss.n = len(ostr_l)
        return ss

    def get_set(self, hero_opts, board, opp_n, tl_ms, kind, n_max):
        key = (len(board), opp_n, hero_opts)
        s = self.sets.get(key)
        if s is not None:
            return s
        if tl_ms < 1500:
            return None
        tb = self.mc_budget(tl_ms, kind)
        if tb < 0.003:
            return None  # too little time for a useful simulation: cheap heuristic instead
        s = self.build(hero_opts, board, opp_n, n_max, tb)
        self.sets[key] = s
        return s

    # ------------------------------------------------------------ pressure k
    def pressure_k(self, req):
        street = req.get("street")
        hist = req.get("history") or []
        cur = 0
        prior = 0
        pre_reraise = 0
        for e in hist:
            if e.get("actor") == "opp" and e.get("action") == "raise":
                if e.get("street") == street:
                    cur += 1
                elif e.get("street") == "preflop":
                    pre_reraise += 1
                else:
                    prior += 1
        k = 0.0
        to_call = req.get("to_call", 0)
        pot = req.get("pot", 0)
        if to_call > 0:
            ratio = to_call / float(max(1, pot - to_call))
            k = 0.9 + min(ratio, 1.5)
            if cur >= 2:
                k += 0.6 * (cur - 1)
        k += 0.35 * prior
        if pre_reraise >= 2:
            k += 0.25
        return clamp(k * self.k_mult(), 0.0, 3.2)

    # ------------------------------------------------------------- raise util
    def make_raise(self, req, target):
        mn = int(req["min_raise"])
        mx = int(req["max_raise"])
        t = int(round(target))
        if t < mn:
            t = mn
        if t > mx:
            t = mx
        invest = t - int(req.get("my_bet", 0))
        if mx - t < 0.4 * max(1, invest):
            t = mx  # pot-committed: just shove
        return {"type": "action", "action": "raise", "amount": int(t)}

    # --------------------------------------------------------------- preflop
    def preflop(self, req):
        legal = req["legal_actions"]
        rng = self.rng
        to_call = req["to_call"]
        pot = req["pot"]
        my_bet = req["my_bet"]
        opp_bet = req["opp_bet"]
        my_stack = req["my_stack"]
        L = 4 - int(req.get("raises_left", 0))
        p = pf_pct(self.hole)
        ace = any((c >> 2) == 12 for c in self.hole)
        can_raise = "raise" in legal and "min_raise" in req and "max_raise" in req
        r = rng.random()
        dm = self.defend_mult()

        def go_raise(target):
            if can_raise:
                return self.make_raise(req, target)
            return CALL if "call" in legal else CHECK

        if to_call <= 0:
            # big blind, small blind limped: isolate or check
            if not can_raise:
                return CHECK
            pr = 0.9 if p >= 0.9 else (0.72 if p >= 0.25 else 0.35)
            if r < pr:
                return go_raise(rng.choice((6, 7, 7, 8, 9)))
            return CHECK

        heavy = opp_bet >= 70 or to_call >= my_stack
        if heavy:
            if can_raise and p >= 0.94 and r < 0.8:
                return go_raise(req["max_raise"])
            if p >= 0.52:
                return CALL
            if p >= 0.35 and r < 0.10:
                return CALL
            return FOLD

        if L <= 1:
            # small blind / button, first to act
            if p < 0.08:
                if r < 0.55:
                    return FOLD
                if r < 0.80:
                    return go_raise(rng.choice((5, 6, 7)))
                return CALL
            if p >= 0.9:
                if r < 0.95:
                    return go_raise(rng.choice((6, 7, 8, 9)))
                return CALL
            if r < 0.88:
                return go_raise(rng.choice((5, 6, 6, 7)))
            return CALL

        if L == 2:
            # facing an open raise
            x = opp_bet / 2.0
            fold_thr = clamp((0.16 + 0.035 * max(0.0, x - 3.0)) * dm, 0.05, 0.5)
            bluff3 = 0.11 + (0.08 if ace else 0.0)
            frac = rng.uniform(0.70, 1.0)
            tgt = opp_bet + frac * (pot + to_call)
            if p >= 0.86:
                return go_raise(tgt) if (can_raise and r < 0.9) else CALL
            if p >= 0.66:
                return go_raise(tgt) if (can_raise and r < 0.30) else CALL
            if p >= fold_thr:
                if can_raise and r < bluff3 * (1.0 if p < 0.5 else 0.7):
                    return go_raise(tgt)
                return CALL
            if can_raise and r < 0.12:
                return go_raise(tgt)
            if r < 0.25:
                return CALL
            return FOLD

        if L == 3:
            # facing a 3-bet
            fold_thr = (0.30 + (0.12 if opp_bet >= 30 else 0.0)) * dm
            frac = rng.uniform(0.70, 1.0)
            tgt = opp_bet + frac * (pot + to_call)
            if can_raise:
                if p >= 0.90 and r < 0.85:
                    return go_raise(tgt)
                if 0.45 <= p < 0.80 and r < 0.09 + (0.10 if ace else 0.0):
                    return go_raise(tgt)
            if p >= fold_thr:
                return CALL
            if r < 0.15:
                return CALL
            return FOLD

        # facing a 4-bet (no more raises) or deeper
        thr = 0.50 if opp_bet < 50 else 0.58
        if p >= thr:
            return CALL
        if r < 0.10:
            return CALL
        return FOLD

    # -------------------------------------------------------------- postflop
    def flop_opts(self):
        h = sorted(self.hole)
        return ((h[0], h[1]), (h[0], h[2]), (h[1], h[2]))

    def hero_equity(self, req, k):
        """Equity of the current hand vs the (weighted) opponent range."""
        board = parse_cards(req["board"])
        tl = req.get("time_left_ms", 60000)
        street = req["street"]
        if street == "flop" and len(self.hole) == 3:
            opts = self.flop_opts()
            ss = self.get_set(opts, board, 3, tl, "flop", 320)
            if ss is None or ss.n == 0:
                return max(quick_eq(o, board) for o in opts)
            eqs = ss.equities(k)
            best = max(eqs)
            if ss.n < 24:
                q = max(quick_eq(o, board) for o in opts)
                best = 0.5 * best + 0.5 * q
            return best
        hole = self.hole
        if len(hole) == 3:  # discard result missing: assume engine kept the best two
            d = lowest_card(hole)
            hole = [c for c in hole if c != d]
        opts = ((min(hole), max(hole)),)
        kind = "turn" if len(board) == 4 else "river"
        ss = self.get_set(opts, board, 2, tl, kind, 300 if kind == "turn" else 400)
        if ss is None or ss.n == 0:
            return quick_eq(hole, board)
        eq = ss.equities(k)[0]
        if ss.n < 24:
            eq = 0.5 * eq + 0.5 * quick_eq(hole, board)
        return eq

    def post_decide(self, req, eq):
        legal = req["legal_actions"]
        rng = self.rng
        si = STREET_IDX.get(req["street"], 0)
        pot = req["pot"]
        to_call = req["to_call"]
        opp_bet = req["opp_bet"]
        my_stack = req["my_stack"]
        can_raise = "raise" in legal and "min_raise" in req and "max_raise" in req
        r = rng.random()
        bm = self.bluff_mult()
        if to_call <= 0:
            if not can_raise:
                return CHECK
            if eq >= 0.62:
                pb = (0.88, 0.90, 0.93)[si]
                if eq >= 0.88 and si < 2:
                    pb = 0.72  # occasionally trap
                frac = rng.uniform(0.70, 1.0)
            elif eq >= 0.40:
                pb = (0.78, 0.72, 0.62)[si]
                frac = rng.uniform(0.60, 0.85)
            else:
                pb = (0.60, 0.55, 0.48)[si] * bm
                frac = rng.uniform(0.60, 0.90)
            if r < min(pb, 0.95):
                return self.make_raise(req, opp_bet + frac * pot)
            return CHECK

        call_cost = min(to_call, my_stack)
        required = call_cost / float(max(1, pot + call_cost))
        kc = (0.74, 0.82, 0.90)[si] * self.call_mult()
        thr = max(0.10, required * kc)
        n_left = req.get("raises_left", 0)
        if can_raise:
            if eq >= 0.72:
                pr = 0.78 if n_left > 1 else 0.55
            elif eq >= 0.50:
                pr = 0.22 if n_left > 1 else 0.08
            elif eq >= thr:
                pr = 0.08 if n_left > 1 else 0.03
            else:
                pr = (0.12 if n_left > 1 else 0.05) * bm
            if r < pr:
                frac = rng.uniform(0.65, 1.0)
                return self.make_raise(req, opp_bet + frac * (pot + to_call))
        if eq >= thr:
            return CALL
        if required < 0.40 and rng.random() < 0.12:
            return CALL
        return FOLD

    # ------------------------------------------------------------- top level
    def decide_action(self, req):
        if req.get("street") == "preflop":
            return self.preflop(req)
        k = self.pressure_k(req)
        if req.get("street") == "flop":
            self.k_flop = k
        eq = self.hero_equity(req, k)
        return self.post_decide(req, eq)

    def decide_discard(self, req):
        hole = sorted(parse_cards(req["hole_cards"]))
        board = parse_cards(req["board"])
        if len(hole) != 3:
            return CARD_STR[lowest_card(hole)]
        self.hole = hole
        tl = req.get("time_left_ms", 60000)
        opts = ((hole[0], hole[1]), (hole[0], hole[2]), (hole[1], hole[2]))
        drop = (hole[2], hole[1], hole[0])
        ss = self.get_set(opts, board, 3, tl, "flop", 320)
        if ss is not None and ss.n > 0:
            eqs = ss.equities(self.k_flop)
        else:
            eqs = [quick_eq(o, board) for o in opts]
        best = 0
        best_v = -1.0
        for i in range(3):
            v = eqs[i] + 0.0005 * ((opts[i][0] >> 2) + (opts[i][1] >> 2))
            if v > best_v:
                best_v = v
                best = i
        return CARD_STR[drop[best]]

    # --------------------------------------------------------------- fallback
    @staticmethod
    def fallback_action(req):
        legal = req.get("legal_actions") or []
        if "check" in legal:
            return CHECK
        if "call" in legal:
            try:
                if req.get("to_call", 0) <= 0.4 * max(1, req.get("pot", 0)):
                    return CALL
            except Exception:
                pass
            if "fold" in legal:
                return FOLD
            return CALL
        if "fold" in legal:
            return FOLD
        return CHECK

    @staticmethod
    def sanitize(reply, req):
        """Make sure the reply is legal; otherwise return a simple legal action."""
        legal = req.get("legal_actions") or []
        act = reply.get("action")
        if act not in legal:
            return Bot.fallback_action(req)
        if act == "raise":
            try:
                a = int(reply["amount"])
                mn = int(req["min_raise"])
                mx = int(req["max_raise"])
            except Exception:
                return Bot.fallback_action(req)
            if mn > mx:
                return Bot.fallback_action(req)
            a = max(mn, min(mx, a))
            return {"type": "action", "action": "raise", "amount": a}
        return {"type": "action", "action": act}

    def safe_action(self, req):
        try:
            reply = self.decide_action(req)
        except Exception as ex:  # never let anything escape
            self._log("action error: %r" % (ex,))
            reply = self.fallback_action(req)
        try:
            return self.sanitize(reply, req)
        except Exception:
            return CHECK

    def safe_discard(self, req):
        try:
            card = self.decide_discard(req)
            if card not in (req.get("hole_cards") or []):
                raise ValueError("discard not in hand")
        except Exception as ex:
            self._log("discard error: %r" % (ex,))
            cards = req.get("hole_cards") or ["2c", "2d", "2h"]
            try:
                card = CARD_STR[lowest_card(parse_cards(cards))]
            except Exception:
                card = cards[0]
        return {"type": "discard", "card": card}

    def _log(self, s):
        self.errors += 1
        if self.errors <= 20:
            try:
                sys.stderr.write(s + "\n")
                sys.stderr.flush()
            except Exception:
                pass

    # ---------------------------------------------------------------- events
    def on_init(self, msg):
        try:
            self.total_hands = int(msg.get("total_hands", 400))
            self.time_bank_ms = int(msg.get("time_bank_ms", 60000))
        except Exception:
            pass

    def on_new_hand(self, msg):
        self.hand_id = int(msg.get("hand_id", self.hand_id + 1))
        self.seat = msg.get("seat", "button")
        self.hole = sorted(parse_cards(msg["hole_cards"]))
        self.dead = []
        self.my_discard = None
        self.opp_discard = None
        self.flop = None
        self.fkc = {}
        self.sets = {}
        self.k_flop = 0.0

    def on_discard_result(self, msg):
        self.hole = sorted(parse_cards(msg["hole_cards"]))
        self.my_discard = CARD_ID.get(msg.get("my_discard"))
        self.opp_discard = CARD_ID.get(msg.get("opp_discard"))
        self.dead = [c for c in (self.my_discard, self.opp_discard) if c is not None]

    def on_hand_result(self, msg):
        self.update_stats(msg.get("history") or [])

    def handle(self, msg):
        """Returns a reply dict, 'stop', or None."""
        t = msg.get("type")
        if t == "action_request":
            return self.safe_action(msg)
        if t == "discard_request":
            return self.safe_discard(msg)
        if t == "init":
            self.on_init(msg)
        elif t == "new_hand":
            self.on_new_hand(msg)
        elif t == "discard_result":
            self.on_discard_result(msg)
        elif t == "hand_result":
            self.on_hand_result(msg)
        elif t == "match_end":
            return "stop"
        return None


def main():
    bot = Bot()
    out = sys.stdout
    inp = sys.stdin
    while True:
        try:
            line = inp.readline()
        except Exception:
            break
        if not line:
            break  # EOF
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        try:
            reply = bot.handle(msg)
        except Exception as ex:
            bot._log("handler error: %r" % (ex,))
            t = msg.get("type")
            if t == "action_request":
                reply = bot.fallback_action(msg)
            elif t == "discard_request":
                reply = bot.safe_discard(msg)
            else:
                reply = None
        if reply == "stop":
            break
        if reply is not None:
            try:
                out.write(json.dumps(reply) + "\n")
                out.flush()
            except Exception:
                break


if __name__ == "__main__":
    main()
