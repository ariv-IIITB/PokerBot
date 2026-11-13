#!/usr/bin/env python3
"""h1_balanced: a theory-minded balanced Discard Hold'em bot (heads-up, JSON-lines protocol).

Style: pot-geometry sizes (~1/3, 2/3, pot), bluff share = s/(1+2s) of a betting range,
minimum-defence-frequency calls, equity realisation (position), Monte-Carlo equity against an
opponent range weighted by that opponent's actions and revealed discard.
Stdlib only. stdout carries protocol messages only; debug goes to stderr.
"""
import sys
import json
import random
import time
from bisect import bisect_left, bisect_right
from itertools import product

RANKS = "23456789TJQKA"
SUITS = "shdc"
DEBUG = bool(__import__("os").environ.get("H1_DEBUG"))
STREETS = ("preflop", "flop", "turn", "river")


def pc(s):
    return RANKS.index(s[0]) * 4 + SUITS.index(s[1])


def fc(c):
    return RANKS[c >> 2] + SUITS[c & 3]


# --------------------------------------------------------------------------- evaluator
# card = rank*4 + suit (rank 0..12 = 2..A). Non-flush hands are looked up by a base-5 rank-count key.
PW = [5 ** (c >> 2) for c in range(52)]
SPW = [1 << (3 * (c & 3)) for c in range(52)]
_pw = PW.__getitem__
_sp = SPW.__getitem__

STRAIGHT_TOP = [-1] * 8192
for _m in range(8192):
    _t = -1
    for _top in range(12, 3, -1):
        _w = 0b11111 << (_top - 4)
        if _m & _w == _w:
            _t = _top
            break
    if _t < 0 and (_m & 0x100F) == 0x100F:
        _t = 3                                     # the wheel
    STRAIGHT_TOP[_m] = _t
OUTS = [0] * 8192                                  # ranks that would complete a straight
for _m in range(8192):
    if STRAIGHT_TOP[_m] < 0:
        OUTS[_m] = sum(1 for _r in range(13) if not (_m >> _r) & 1 and STRAIGHT_TOP[_m | (1 << _r)] >= 0)

FLUSH_SUIT = {}
for _n in product(range(8), repeat=4):
    if 5 <= sum(_n) <= 7 and max(_n) >= 5:
        FLUSH_SUIT[sum(v << (3 * i) for i, v in enumerate(_n))] = _n.index(max(_n))
FLUSH_CACHE = {}
_T = {}


def _pack(cat, rs):
    v = cat
    for i in range(5):
        v = (v << 4) | (rs[i] if i < len(rs) else 0)
    return v


def _flush_score(mask):
    t = STRAIGHT_TOP[mask]
    if t >= 0:
        return _pack(8, [t])
    return _pack(5, [r for r in range(12, -1, -1) if (mask >> r) & 1][:5])


def _nf(k):
    cnt = []
    for _ in range(13):
        cnt.append(k % 5)
        k //= 5
    quads, trips, pairs, allr = [], [], [], []
    mask = 0
    for r in range(12, -1, -1):
        n = cnt[r]
        if n:
            mask |= 1 << r
            allr.append(r)
            if n == 4:
                quads.append(r)
            elif n == 3:
                trips.append(r)
            elif n == 2:
                pairs.append(r)
    if quads:
        q = quads[0]
        return _pack(7, [q] + [r for r in allr if r != q][:1])
    if trips and (len(trips) > 1 or pairs):
        rest = sorted(trips[1:] + pairs, reverse=True)
        return _pack(6, [trips[0], rest[0]])
    st = STRAIGHT_TOP[mask]
    if st >= 0:
        return _pack(4, [st])
    if trips:
        t = trips[0]
        return _pack(3, [t] + [r for r in allr if r != t][:2])
    if len(pairs) >= 2:
        p1, p2 = pairs[0], pairs[1]
        return _pack(2, [p1, p2] + [r for r in allr if r != p1 and r != p2][:1])
    if pairs:
        p = pairs[0]
        return _pack(1, [p] + [r for r in allr if r != p][:3])
    return _pack(0, allr[:5])


def ev(cs):
    """Score of the best 5-card hand among 5..7 cards (higher wins)."""
    fs = FLUSH_SUIT.get(sum(map(_sp, cs)))
    if fs is not None:
        m = 0
        for c in cs:
            if c & 3 == fs:
                m |= 1 << (c >> 2)
        v = FLUSH_CACHE.get(m)
        if v is None:
            v = FLUSH_CACHE[m] = _flush_score(m)
        return v
    k = sum(map(_pw, cs))
    v = _T.get(k)
    if v is None:
        v = _T[k] = _nf(k)
    return v


CAT = 1 << 20
DRAW_BONUS = int(0.45 * CAT)


def draw_flag(h, board):
    """1 = flush draw / open-ended straight draw using a hole card, 0.5 = gutshot, else 0."""
    fl = 0
    for s in {c & 3 for c in h}:
        n = sum(1 for c in h if c & 3 == s) + sum(1 for c in board if c & 3 == s)
        if n == 4:
            fl = 1
    hm = bm = 0
    for c in h:
        hm |= 1 << (c >> 2)
    for c in board:
        bm |= 1 << (c >> 2)
    m = hm | bm
    st = 0
    if STRAIGHT_TOP[m] < 0:
        oa = OUTS[m]
        if oa > OUTS[bm]:
            st = 1 if oa >= 2 else 0.5
    return fl if fl > st else st


def hand_val(h, board, with_draw):
    raw = ev(list(h) + board)
    d = draw_flag(h, board) if with_draw else 0
    return raw, d


# --------------------------------------------------------------------------- preflop strength
CHEN = [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6, 7, 8, 10]


def chen(a, b):
    ra, rb = a >> 2, b >> 2
    hi, lo = (ra, rb) if ra >= rb else (rb, ra)
    p = CHEN[hi]
    if ra == rb:
        return max(5.0, 2 * p)
    if a & 3 == b & 3:
        p += 2
    gap = hi - lo - 1
    p -= (0, 1, 2, 4, 5)[gap if gap < 4 else 4]
    if gap <= 1 and hi < 10:
        p += 1
    return p


def pf3(h):
    a, b, c = h
    s = sorted((chen(a, b), chen(a, c), chen(b, c)), reverse=True)
    v = s[0] + 0.35 * s[1]
    if a & 3 == b & 3 == c & 3:
        v += 1.5
    ranks = sorted((a >> 2, b >> 2, c >> 2))
    if ranks[0] == ranks[2]:
        v += 3
    elif ranks[2] - ranks[0] <= 4 and ranks[0] != ranks[1] != ranks[2]:
        v += 1.5
    return v


_r0 = random.Random(7)
PF_SORTED = sorted(pf3(_r0.sample(range(52), 3)) for _ in range(4000))


def pf_pct(h):
    v = pf3(h)
    return (bisect_left(PF_SORTED, v) + bisect_right(PF_SORTED, v)) / (2.0 * len(PF_SORTED))


# --------------------------------------------------------------------------- opponent-range weights
def weight_rec(rec, praw, padj, dr, river):
    """Relative likelihood of a holding (strength percentile praw/padj, draw flag dr) given one
    opponent action rec = (street, kind, size, level, opp_in_position)."""
    st, kind, s, lvl, ip = rec
    if st == 0:
        p = padj
        if kind == "check":
            w = 1.0 if p < 0.65 else 0.4
        elif kind == "call":
            if lvl <= 1:
                w = 0.5 if p > 0.85 else (1.0 if p > 0.1 else 0.2)
            else:
                hi = 0.88 if lvl == 2 else 0.93
                lo = 0.40 if lvl == 2 else 0.50
                w = 0.5 if p > hi else (1.0 if p >= lo else 0.1)
        else:
            if lvl <= 2:
                w = 1.0 if p >= 0.28 else 0.15
            elif lvl == 3:
                w = 1.0 if p >= 0.82 else (0.2 if p >= 0.45 else 0.1)
            else:
                w = 1.0 if p >= 0.92 else 0.06
    elif kind in ("bet", "raise"):
        fv = 0.42 / (1 + 1.2 * s) * (0.6 if kind == "raise" else 1.0)
        r = s / (1 + s)
        if padj >= 1 - fv:
            w = 1.0
        elif praw < 0.35:
            d = 2.0 if (dr >= 1 and not river) else (1.4 if dr > 0 and not river else 1.0)
            w = r * fv / 0.35 * d
        else:
            w = 0.04
    elif kind == "call":
        m = 1.0 / (1.0 + s)
        if padj > 0.9:
            w = 0.5
        elif padj >= 1 - m:
            w = 1.0
        else:
            w = 0.08 + (0.5 if (dr >= 1 and not river) else 0.0)
    else:  # check
        cap = 0.25 if ip else 0.15
        w = 0.45 if padj > 1 - cap else 1.0
    return 0.12 + 0.88 * w


def pct_of(sorted_vals, v):
    n = len(sorted_vals)
    return (bisect_left(sorted_vals, v) + bisect_right(sorted_vals, v)) / (2.0 * n)


# --------------------------------------------------------------------------- the bot
class Bot:
    def __init__(self):
        self.rng = random.Random()
        self.total = 200
        self.bank_ms = 30000
        self.tl = 30000
        self.hid = 1
        self.seat = "button"
        self.hole = []
        self.keep = None
        self.mydisc = None
        self.oppdisc = None
        self.board = []

    # ---- messages
    def on_init(self, m):
        self.total = int(m.get("total_hands", 200))
        self.bank_ms = self.tl = int(m.get("time_bank_ms", 30000))

    def on_new_hand(self, m):
        self.hid = int(m.get("hand_id", self.hid + 1))
        self.seat = m.get("seat", "button")
        self.hole = [pc(c) for c in m["hole_cards"]]
        self.keep = None
        self.mydisc = None
        self.oppdisc = None
        self.board = []
        self._hist = []
        self._rep = None
        self._rstreet = ""

    def on_discard_result(self, m):
        self.keep = [pc(c) for c in m["hole_cards"]]
        self.mydisc = pc(m["my_discard"])
        self.oppdisc = pc(m["opp_discard"])

    def scale(self):
        rem = max(1, self.total - self.hid + 1)
        per_hand = self.tl / rem
        return max(0.3, min(1.2, per_hand / 140.0))

    # ---- history
    def parse_history(self, hist):
        me_btn = self.seat == "button"
        bets = {"me": 1 if me_btn else 2, "opp": 2 if me_btn else 1}
        prev = 0
        cur = "preflop"
        lvl = 1
        line = []
        pf_aggr = None
        opp_aggr_streets = set()
        for h in hist:
            st = h.get("street")
            if st != cur:
                prev += max(bets.values())
                bets = {"me": 0, "opp": 0}
                cur = st
                lvl = 0
            a = h.get("actor")
            o = "opp" if a == "me" else "me"
            act = h.get("action")
            amt = h.get("amount")
            sidx = STREETS.index(st) if st in STREETS else 0
            pot = 2 * prev + bets["me"] + bets["opp"]
            facing = max(0, bets[o] - bets[a])
            ipf = not me_btn                      # the opponent is the button
            if act == "check":
                rec = (sidx, "check", 0.0, lvl, ipf)
            elif act == "call":
                rec = (sidx, "call", facing / max(1, pot - facing), lvl, ipf)
                bets[a] = amt if amt is not None else bets[o]
            elif act == "raise":
                if facing == 0 and sidx > 0:
                    kind, s = "bet", (amt or 0) / max(1, pot)
                else:
                    kind, s = "raise", ((amt or 0) - bets[o]) / max(1, pot + facing)
                lvl += 1
                bets[a] = amt or bets[a]
                rec = (sidx, kind, max(0.05, s), lvl, ipf)
                if sidx == 0:
                    pf_aggr = a
                if a == "opp":
                    opp_aggr_streets.add(sidx)
            else:
                continue
            if a == "opp":
                line.append(rec)
        return line, pf_aggr, opp_aggr_streets

    # ---- sampling machinery
    def best_keep(self, h3, board3):
        """Heuristic best 2-card keep of 3 on a 3-card flop: (keep, value, raw, draw)."""
        best = None
        for i in range(3):
            k = (h3[(i + 1) % 3], h3[(i + 2) % 3])
            raw = ev(list(k) + board3)
            if best is None or raw > best[2]:
                best = (k, raw, i)
        res = None
        if best[1] < CAT:                       # no pair: draws decide
            for i in range(3):
                k = (h3[(i + 1) % 3], h3[(i + 2) % 3])
                raw = ev(list(k) + board3)
                d = draw_flag(k, board3)
                v = raw + int(DRAW_BONUS * d)
                if res is None or v > res[1]:
                    res = (k, v, raw, d)
            return res
        k, raw, _ = best
        return (k, raw, raw, 0.0)

    def build_pool(self, board, street, mycards, n, line, deadline):
        """Opponent holding samples, weighted by the opponent's actions.
        Returns (items, unseen, my_pct, my_draw) with items = (K, exclude, weight)."""
        rng = self.rng
        post = street >= 2
        dead = set(mycards) | set(board)
        if self.mydisc is not None:
            dead.add(self.mydisc)
        if self.oppdisc is not None:
            dead.add(self.oppdisc)
        unseen = [c for c in range(52) if c not in dead]
        x = self.oppdisc
        h3s = []
        for _ in range(n):
            if post:
                K = tuple(rng.sample(unseen, 2))
                h3s.append((K, K + (x,)))
            else:
                h3s.append((None, tuple(rng.sample(unseen, 3))))
        streets = {r[0] for r in line} | {street}
        P = {}
        Ks = [p[0] for p in h3s]
        board_by = {1: board[:3], 2: board[:4], 3: board[:5]}
        for g in streets:
            if g == 0:
                pr = [pf_pct(p[1]) for p in h3s]
                P[0] = (pr, pr, [0.0] * n)
                continue
            raws, advs, drs = [], [], []
            bd = board_by[g]
            for i, (K, h3) in enumerate(h3s):
                if g == 1:
                    k, v, raw, d = self.best_keep(h3, bd)
                    if not post and g == street:
                        Ks[i] = k
                    raws.append(raw)
                    advs.append(v)
                    drs.append(d)
                else:
                    raw = ev(list(K) + bd)
                    d = draw_flag(K, bd) if g < 3 else 0.0
                    raws.append(raw)
                    advs.append(raw + int(DRAW_BONUS * d))
                    drs.append(d)
            sr, sa = sorted(raws), sorted(advs)
            P[g] = ([pct_of(sr, v) for v in raws], [pct_of(sa, v) for v in advs], drs, sa)
        items = []
        for i, (K, h3) in enumerate(h3s):
            w = 1.0
            for rec in line:
                g = rec[0]
                pr, pa, dr = P[g][0][i], P[g][1][i], P[g][2][i]
                w *= weight_rec(rec, pr, pa, dr, g == 3)
            k = Ks[i]
            if post:
                # the opponent's discard x says something about the kept pair
                rk = k[0] >> 2, k[1] >> 2
                xr = x >> 2
                bR = {c >> 2 for c in board[:3]}
                bS = [c & 3 for c in board[:3]]
                if xr > max(rk) and xr not in rk:
                    w *= 0.4
                if xr in bR and rk[0] not in bR and rk[1] not in bR:
                    w *= 0.35
                if bS.count(x & 3) >= 2 and (k[0] & 3) != (x & 3) and (k[1] & 3) != (x & 3):
                    w *= 0.5
            items.append((k, k if post else h3s[i][1], w))
        # my own percentile among random holdings on the current street
        my_pct, my_draw, my_keep = 0.5, 0.0, None
        bd = board_by.get(street, board)
        if street == 1:
            kk, v, raw, d = self.best_keep(tuple(mycards), bd)
            my_keep, my_draw = kk, d
            my_pct = pct_of(P[1][3], v)
        elif street >= 2:
            raw = ev(list(mycards) + bd)
            d = draw_flag(mycards, bd) if street < 3 else 0.0
            my_draw = d
            my_pct = pct_of(P[street][3], raw + int(DRAW_BONUS * d))
        return items, unseen, my_pct, my_draw, my_keep

    def mc_equity(self, me2, board, items, unseen, deadline):
        need = 5 - len(board)
        rng = self.rng
        ws = wr = 0.0
        base = list(me2) + board
        for idx, (K, ex, w) in enumerate(items):
            if need:
                rs = rng.sample(unseen, need + len(ex))
                run = [c for c in rs if c not in ex][:need]
            else:
                run = []
            a = ev(base + run)
            b = ev(list(K) + board + run)
            ws += w
            if a > b:
                wr += w
            elif a == b:
                wr += 0.5 * w
            if idx & 31 == 31 and time.perf_counter() > deadline:
                break
        return wr / ws if ws > 0 else 0.5

    # ---- discard
    def choose_discard(self, m):
        h3 = [pc(c) for c in m["hole_cards"]]
        board = [pc(c) for c in m["board"]]
        self.tl = m.get("time_left_ms", self.tl)
        t0 = time.perf_counter()
        deadline = t0 + 0.05
        hist = list(getattr(self, "_hist", []))
        rep = getattr(self, "_rep", None)
        if rep and rep.get("action") in ("raise", "call", "check") and getattr(self, "_rstreet", "") == "flop":
            hist.append({"street": "flop", "actor": "me", "action": rep["action"],
                         **({"amount": rep["amount"]} if rep.get("action") == "raise" else {})})
            if rep["action"] == "raise":                # the flop ended, so the opponent called
                hist.append({"street": "flop", "actor": "opp", "action": "call", "amount": rep["amount"]})
        line, _, _ = self.parse_history(hist)
        n = int(180 * self.scale())
        items, unseen, _, _, _ = self.build_pool(board, 1, h3, n, line, deadline)
        keeps = [(h3[1], h3[2]), (h3[0], h3[2]), (h3[0], h3[1])]       # drop h3[0], h3[1], h3[2]
        wins = [0.0, 0.0, 0.0]
        ws = 0.0
        rng = self.rng
        for idx, (K, ex, w) in enumerate(items):
            rs = rng.sample(unseen, 2 + len(ex))
            run = [c for c in rs if c not in ex][:2]
            full = board + run
            b = ev(list(K) + full)
            for j in range(3):
                a = ev(list(keeps[j]) + full)
                wins[j] += w if a > b else (0.5 * w if a == b else 0.0)
            ws += w
            if idx & 31 == 31 and time.perf_counter() > deadline:
                break
        # tie-break with the static heuristic value
        best, bv = 0, -1.0
        for j in range(3):
            bk = keeps[j]
            raw = ev(list(bk) + board)
            d = draw_flag(bk, board)
            v = (wins[j] / ws if ws else 0.5) + 1e-9 * (raw + DRAW_BONUS * d) / CAT
            if v > bv:
                best, bv = j, v
        return h3[best]

    # ---- actions
    def act(self, m):
        self.tl = m.get("time_left_ms", self.tl)
        c = {
            "street": STREETS.index(m["street"]),
            "board": [pc(x) for x in m["board"]],
            "pot": m["pot"], "my_bet": m["my_bet"], "opp_bet": m["opp_bet"],
            "to_call": m["to_call"], "my_stack": m["my_stack"], "opp_stack": m["opp_stack"],
            "legal": m["legal_actions"], "min_raise": m.get("min_raise"),
            "max_raise": m.get("max_raise"), "raises_left": m.get("raises_left", 0),
        }
        line, pf_aggr, opp_aggr = self.parse_history(m.get("history", []))
        self._hist = m.get("history", [])
        self._rstreet = m["street"]
        c["line"], c["pf_aggr"], c["opp_aggr"] = line, pf_aggr, opp_aggr
        c["ip"] = self.seat == "button"
        if c["street"] == 0:
            return self.preflop(c)
        return self.postflop(c)

    def clamp_raise(self, c, to):
        lo, hi = c["min_raise"], c["max_raise"]
        to = int(round(to))
        # commit rule: a big share of the stack goes all-in
        tot = c["my_bet"] + c["my_stack"]
        if to >= 0.55 * tot or (tot - to) < 0.35 * (c["pot"] + 2 * (to - c["my_bet"])):
            to = hi
        return max(lo, min(hi, to))

    def R(self, c, to):
        return {"type": "action", "action": "raise", "amount": self.clamp_raise(c, to)}

    @staticmethod
    def A(a):
        return {"type": "action", "action": a}

    def passive(self, c):
        return self.A("check") if "check" in c["legal"] else self.A("fold")

    # ---- preflop
    def preflop(self, c):
        rng = self.rng
        u = rng.random()
        h3 = self.hole
        pp = pf_pct(h3)
        legal = c["legal"]
        can_raise = "raise" in legal
        to_call, pot = c["to_call"], c["pot"]
        lvl = 4 - c["raises_left"]
        if to_call == 0:                                    # BB with the option vs a limp
            if can_raise and ((pp >= 0.55 and u < 0.85) or (pp < 0.18 and u < 0.25)):
                return self.R(c, 6)
            return self.A("check")
        if c["ip"] and lvl <= 1:                            # SB first in
            if pp >= 0.30:
                if can_raise:
                    big = pp >= 0.5 and rng.random() < 0.3
                    return self.R(c, 6 if big else 5)
                return self.A("call")
            if pp >= 0.08 and u < 0.8:
                return self.A("call")
            return self.A("fold")
        # facing a raise
        pot_before = max(1, pot - to_call)
        m = pot_before / (pot_before + to_call)
        adj = 0.9 if c["ip"] else 0.8
        T = max(0.12, 1 - m * adj)
        cf = to_call / max(1, c["my_stack"])
        if cf > 0.35:
            T = max(T, 0.85)
        if cf > 0.6:
            T = max(T, 0.92)
        ob = c["opp_bet"]
        if can_raise:
            if lvl <= 2 and pp >= 0.86 and u < 0.9:
                return self.R(c, ob * 3)
            if lvl == 3 and pp >= 0.94 and u < 0.9:
                return self.R(c, ob * 2.4)
            if lvl >= 4 and pp >= 0.95:
                return self.R(c, c["max_raise"])
            if lvl <= 2 and T - 0.13 <= pp < T and u < 0.35 and cf < 0.2:
                return self.R(c, ob * 3)
            if lvl == 3 and T - 0.08 <= pp < T and u < 0.3 and cf < 0.4:
                return self.R(c, ob * 2.3)
        if pp >= T:
            return self.A("call")
        return self.A("fold")

    # ---- postflop
    def postflop(self, c):
        rng = self.rng
        street = c["street"]
        board = c["board"]
        mycards = self.hole if street == 1 else (self.keep or self.hole[:2])
        if street >= 2 and len(mycards) > 2:
            mycards = mycards[:2]
        n = int((150 if street < 3 else 190) * self.scale())
        deadline = time.perf_counter() + 0.06
        items, unseen, pct, dm, mykeep = self.build_pool(board, street, mycards, n, c["line"], deadline)
        me2 = mykeep if street == 1 else mycards
        eq = self.mc_equity(me2, board, items, unseen, deadline)
        to_call, pot = c["to_call"], c["pot"]
        legal = c["legal"]
        can_raise = "raise" in legal
        ip = c["ip"]
        river = street == 3
        u = rng.random()
        if to_call == 0:
            if not can_raise:
                return self.A("check")
            init = c["pf_aggr"] == "me"
            earlier_opp_aggr = any(s < street for s in c["opp_aggr"])
            if eq >= 0.80:
                slow = 0.0 if river else (0.12 if ip else 0.25)
                if u < slow:
                    return self.A("check")
                return self.R(c, (1.0 if river or street == 2 and eq > 0.9 else 0.66) * pot)
            if eq >= 0.62:
                return self.R(c, 0.66 * pot) if u < 0.9 else self.A("check")
            if eq >= 0.52:
                return self.R(c, 0.33 * pot) if u < (0.6 if ip else 0.4) else self.A("check")
            if not river and dm >= 1 and eq >= 0.25:
                return self.R(c, 0.66 * pot) if u < 0.55 else self.A("check")
            if not river and dm >= 0.5 and eq >= 0.25:
                return self.R(c, 0.5 * pot) if u < 0.25 else self.A("check")
            if eq < (0.2 if river else 0.3):
                s = 0.66 if not river else (1.0 if rng.random() < 0.5 else 0.66)
                pb = 0.85 * s / (1 + s)
                pb *= (1.2 if init else 0.8) * (1.0 if ip else 0.85)
                if earlier_opp_aggr:
                    pb *= 0.5
                if u < pb:
                    return self.R(c, s * pot)
            return self.A("check")
        # facing a bet
        req = to_call / (pot + to_call)
        eff = eq * (1.0 if (ip or river or to_call >= c["my_stack"]) else 0.93)
        if dm >= 1 and not river:
            eff += 0.02
        if can_raise:
            if eq >= 0.82 and u < (0.45 if river else 0.7):
                return self.R(c, c["opp_bet"] + 0.8 * (pot + to_call))
            if not river and dm >= 1 and 0.3 <= eq < 0.55 and u < 0.18:
                return self.R(c, c["opp_bet"] + 0.75 * (pot + to_call))
            if eq < 0.2 and not river and u < 0.03:
                return self.R(c, c["opp_bet"] + 0.75 * (pot + to_call))
        if eff >= req + 0.02:
            return self.A("call")
        if eff >= req - 0.02:
            return self.A("call") if rng.random() < 0.5 else self.A("fold")
        mdf = (pot - to_call) / pot if pot > 0 else 0.5
        if pct >= 1 - mdf * 0.8 and eq >= 0.65 * req and to_call < 0.4 * c["my_stack"] and rng.random() < 0.6:
            return self.A("call")
        return self.A("fold")

    # ---- dispatch
    def fallback_action(self, m):
        legal = m.get("legal_actions", [])
        if "check" in legal:
            return self.A("check")
        if "call" in legal and m.get("to_call", 1) <= max(1, 0.15 * m.get("pot", 0)):
            return self.A("call")
        return self.A("fold") if "fold" in legal else self.A(legal[0] if legal else "check")

    def sanitize(self, r, m):
        legal = m.get("legal_actions", [])
        a = r.get("action")
        if a not in legal:
            return self.fallback_action(m)
        if a == "raise":
            amt = int(r.get("amount", 0))
            amt = max(int(m["min_raise"]), min(int(m["max_raise"]), amt))
            return {"type": "action", "action": "raise", "amount": amt}
        return {"type": "action", "action": a}

    def handle(self, m):
        t = m.get("type")
        if t == "init":
            self.on_init(m)
        elif t == "new_hand":
            self.on_new_hand(m)
        elif t == "discard_result":
            self.on_discard_result(m)
        elif t == "action_request":
            try:
                r = self.act(m)
            except Exception as e:          # never crash: a legal fallback
                print("act error: %r" % (e,), file=sys.stderr)
                r = self.fallback_action(m)
            r = self.sanitize(r, m)
            self._rep = r
            return r
        elif t == "discard_request":
            try:
                card = self.choose_discard(m)
                return {"type": "discard", "card": fc(card)}
            except Exception as e:
                print("discard error: %r" % (e,), file=sys.stderr)
                cards = m.get("hole_cards", [])
                worst = min(cards, key=lambda s: RANKS.index(s[0]))
                return {"type": "discard", "card": worst}
        return None


def main():
    bot = Bot()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get("type") == "match_end":
            break
        try:
            r = bot.handle(m)
        except Exception as e:
            print("fatal handler error: %r" % (e,), file=sys.stderr)
            r = None
        if r is not None:
            if DEBUG:
                sys.stderr.write("R %s %s\n" % (m.get("street", "disc"), r.get("action", "discard")))
            sys.stdout.write(json.dumps(r, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
