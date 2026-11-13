#!/usr/bin/env python3
"""h6_discardread: information-driven Discard Hold'em bot (heads-up, JSON lines over stdin/stdout).

Style: reads the opponent's kept pair from its revealed discard (+ the board + its betting),
keeps an explicit weighted posterior over the opponent's kept hands, picks its own discard by
sampled equity against that posterior, then plays equity-vs-range with pot-based sizing.
Python 3.11 stdlib only. stdout = protocol only; debug -> stderr.
"""
import sys
import json
import math
import random
import time

RANKS = "23456789TJQKA"
SUITS = "shdc"


def card(s):
    return RANKS.index(s[0]) * 4 + SUITS.index(s[1])


def cstr(c):
    return RANKS[c >> 2] + SUITS[c & 3]


# --------------------------------------------------------------------------- hand evaluator
_POP = [bin(i).count("1") for i in range(8192)]
_STR = [-1] * 8192            # highest card (rank index) of the best straight in a rank mask


def _build_tables():
    wins = []
    for hi in range(12, 3, -1):
        wins.append((sum(1 << (hi - k) for k in range(5)), hi))
    wins.append((0x100F, 3))  # wheel A2345
    for m in range(8192):
        for w, hi in wins:
            if m & w == w:
                _STR[m] = hi
                break


_build_tables()
_OUTS = [0] * 8192            # number of ranks that complete a straight (when none made)
for _m in range(8192):
    if _STR[_m] < 0:
        _OUTS[_m] = sum(1 for r in range(13) if not _m >> r & 1 and _STR[_m | 1 << r] >= 0)


def _kick(m, n):
    v = 0
    for _ in range(n):
        if m:
            b = m.bit_length() - 1
            m ^= 1 << b
            v = (v << 4) | b
        else:
            v <<= 4
    return v


def evaluate(cards):
    """Score of the best 5-card hand among up to 7 cards (higher = better)."""
    rc = [0] * 13
    sm = [0, 0, 0, 0]
    for c in cards:
        r = c >> 2
        rc[r] += 1
        sm[c & 3] |= 1 << r
    rm = sm[0] | sm[1] | sm[2] | sm[3]
    for m in sm:
        if _POP[m] >= 5:
            st = _STR[m]
            if st >= 0:
                return (8 << 24) | (st << 20)
            return (5 << 24) | (_kick(m, 5) << 4)
    q = t = p1 = p2 = -1
    for r in range(12, -1, -1):
        n = rc[r]
        if n < 2:
            continue
        if n == 4:
            if q < 0:
                q = r
        elif n == 3:
            if t < 0:
                t = r
            elif p1 < 0:
                p1 = r
            elif p2 < 0:
                p2 = r
        else:
            if p1 < 0:
                p1 = r
            elif p2 < 0:
                p2 = r
    if q >= 0:
        return (7 << 24) | (q << 20) | (_kick(rm & ~(1 << q), 1) << 16)
    if t >= 0 and p1 >= 0:
        return (6 << 24) | (t << 20) | (p1 << 16)
    st = _STR[rm]
    if st >= 0:
        return (4 << 24) | (st << 20)
    if t >= 0:
        return (3 << 24) | (t << 20) | (_kick(rm & ~(1 << t), 2) << 12)
    if p2 >= 0:
        return (2 << 24) | (p1 << 20) | (p2 << 16) | (_kick(rm & ~((1 << p1) | (1 << p2)), 1) << 12)
    if p1 >= 0:
        return (1 << 24) | (p1 << 20) | (_kick(rm & ~(1 << p1), 3) << 8)
    return _kick(rm, 5) << 4


def vstrength(h, board):
    """Cheap hand-strength proxy for a kept pair `h` on a 3-5 card board.
    Returns (v, draw): v ~ category + rank fraction (+ draw bonus); draw = draw bonus part."""
    cs = h + board
    s = evaluate(cs)
    cat = s >> 24
    r1 = (s >> 20) & 15
    r2 = (s >> 16) & 15
    v = cat + 0.8 * r1 / 12.0 + 0.1 * r2 / 12.0
    sb = evaluate(board)
    if cat >= 1 and (sb >> 16) == (s >> 16) and (sb >> 24) == cat:
        v -= 0.55                                  # hole cards add nothing but kickers
    draw = 0.0
    nb = len(board)
    if nb < 5 and cat < 5:
        c0, c1 = h
        s0, s1 = c0 & 3, c1 & 3
        cnt = [0, 0, 0, 0]
        for c in cs:
            cnt[c & 3] += 1
        if s0 == s1:
            if cnt[s0] == 4:
                draw = 0.55
            elif cnt[s0] == 3 and nb == 3:
                draw = 0.08
        else:
            if cnt[s0] == 4 or cnt[s1] == 4:
                draw = 0.42
        if cat < 4:
            rm = 0
            for c in cs:
                rm |= 1 << (c >> 2)
            bm = 0
            for c in board:
                bm |= 1 << (c >> 2)
            o = _OUTS[rm] - _OUTS[bm]
            if o >= 2:
                draw += 0.42
            elif o == 1:
                draw += 0.2
        if nb == 4:
            draw *= 0.75
        v += draw
    return v, draw


# --------------------------------------------------------------------------- preflop strength
def _chen2(a, b, suited):
    """Chen-style points for two cards with ranks a>=b (0..12)."""
    def pts(r):
        if r == 12:
            return 10.0
        if r == 11:
            return 8.0
        if r == 10:
            return 7.0
        if r == 9:
            return 6.0
        return (r + 2) / 2.0
    s = pts(a)
    if a == b:
        return max(5.0, 2 * s)
    if suited:
        s += 2
    gap = a - b - 1
    s -= (0, 1, 2, 4, 5)[min(gap, 4)]
    if gap <= 1 and a < 10:
        s += 1
    return s


# Fitted offline: E[equity vs a random hand] ~ linear in the features below.
_PF_COEF = [0.3145, 0.01816, 0.00755, 0.00377, -0.04065, -0.00564, -0.08974, 0.05357, 0.00503]


def _pf_features(h3):
    rk = sorted((c >> 2 for c in h3), reverse=True)
    ss = [c & 3 for c in h3]
    chens = []
    for i, j in ((0, 1), (0, 2), (1, 2)):
        ci, cj = h3[i], h3[j]
        a, b = max(ci >> 2, cj >> 2), min(ci >> 2, cj >> 2)
        chens.append(_chen2(a, b, (ci & 3) == (cj & 3)))
    chens.sort(reverse=True)
    mx = max(ss.count(x) for x in range(4))
    trips = 1.0 if rk[0] == rk[2] else 0.0
    haspair = 1.0 if (rk[0] == rk[1] or rk[1] == rk[2]) else 0.0
    return [1.0, chens[0], chens[1], chens[2], 1.0 if mx == 3 else 0.0, 1.0 if mx == 2 else 0.0,
            trips, haspair, float(rk[0] - rk[2])]


def pf_equity(h3):
    f = _pf_features(h3)
    if _PF_COEF is not None:
        e = sum(a * b for a, b in zip(_PF_COEF, f))
    else:
        e = 0.38 + 0.02 * f[1] + 0.004 * f[2]
    return min(0.9, max(0.25, e))


# --------------------------------------------------------------------------- the bot
class Bot:
    def __init__(self):
        self.rng = random.Random()
        self.total_hands = 400
        self.bank_ms = 60000.0
        self.hand_no = 0
        self.seat = "button"
        self.hole3 = []
        self.kept = []
        self.my_disc = None
        self.opp_disc = None
        self.board_flop = []
        self.opp_acts = []          # [(street, kind, frac)]
        self.dw_cache = {}
        self.time_left = 60.0
        # opponent model (match-long counters, with priors)
        self.disc_n = 0.0
        self.disc_best = 0.0
        self.disc_low = 0.0
        self.resp_fold = 2.0
        self.resp_call = 3.0
        self.resp_raise = 0.5
        self.pf_raise = 2.0
        self.pf_other = 3.0
        self.val_cnt = 0.0
        self.bluff_cnt = 0.0
        self.opp_bets = 0.0         # postflop opp bet/raise count
        self.opp_checks = 0.0

    # ----- helpers on the opponent model
    def alpha(self):
        r = (self.val_cnt + 3.0) / (self.val_cnt + self.bluff_cnt + 4.5)
        return 0.3 + 0.6 * r

    def fold_rate(self):
        return self.resp_fold / (self.resp_fold + self.resp_call + self.resp_raise)

    def call_rate(self):
        return self.resp_call / (self.resp_fold + self.resp_call + self.resp_raise)

    def pfr(self):
        return self.pf_raise / (self.pf_raise + self.pf_other)

    # ----- budgets
    def budget(self):
        hands_left = max(1, self.total_hands - self.hand_no + 1)
        share = self.time_left / (hands_left * 5.3)
        if self.time_left < 1.5:
            return 0.002
        return max(0.003, min(0.040, share * 0.55))

    # ----- history parsing
    def parse_history(self, history):
        """Opponent actions [(street_idx, kind, frac)] and our own actions, with pot-fractions."""
        sidx = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}
        me_bet, opp_bet = (1, 2) if self.seat == "button" else (2, 1)
        base = 0
        cur = 0
        out = []
        mine = []
        for e in history:
            try:
                st = sidx.get(e.get("street"), 0)
                if st != cur:
                    base += me_bet + opp_bet
                    me_bet = opp_bet = 0
                    cur = st
                who = e.get("actor")
                act = e.get("action")
                amt = e.get("amount")
                pot = base + me_bet + opp_bet
                if who == "me":
                    mb, ob = me_bet, opp_bet
                else:
                    mb, ob = opp_bet, me_bet
                frac = 0.0
                kind = act
                if act == "raise":
                    amt = int(amt)
                    frac = max(0.0, (amt - ob) / max(2.0, pot))
                    kind = "raise" if ob > 0 else "bet"
                    mb = amt
                elif act == "call":
                    frac = max(0.0, (ob - mb) / max(2.0, pot))
                    mb = ob
                if who == "me":
                    me_bet = mb
                    mine.append((st, kind, frac))
                else:
                    opp_bet = mb
                    out.append((st, kind, frac))
            except Exception:
                continue
        return out, mine

    # ----- likelihood of the opponent's observed actions given a kept-hand strength v
    @staticmethod
    def _sig(x):
        if x > 30:
            return 1.0
        if x < -30:
            return 0.0
        return 1.0 / (1.0 + math.exp(-x))

    def act_weight(self, v, acts, flop_only=False):
        a = self.alpha()
        w = 1.0
        for st, kind, frac in acts:
            if st == 0:
                continue
            if flop_only and st != 1:
                continue
            ex = 0.6 if st == 1 else 1.0
            if kind == "bet":
                p = 0.10 + 0.82 * self._sig(1.8 * (v - (1.4 + 0.7 * min(frac, 1.5))))
                lik = p
            elif kind == "raise":
                p = 0.06 + 0.88 * self._sig(1.8 * (v - (2.0 + 0.5 * min(frac, 1.5))))
                lik = p
            elif kind == "call":
                lik = 0.35 + 0.65 * math.exp(-((v - 1.5) / 1.4) ** 2)
            elif kind == "check":
                p = 0.10 + 0.82 * self._sig(1.8 * (v - 1.7))
                lik = 1.0 - 0.75 * p
            else:
                continue
            lik = a * lik + (1.0 - a)
            w *= lik ** ex
        return w

    # ----- discard-consistency weight of an opp kept pair given its revealed discard
    def disc_weight(self, pair):
        key = pair if pair[0] < pair[1] else (pair[1], pair[0])
        w = self.dw_cache.get(key)
        if w is not None:
            return w
        a, b = key
        d = self.opp_disc
        fb = self.board_flop
        vab = vstrength([a, b], fb)[0]
        alt = max(vstrength([a, d], fb)[0], vstrength([b, d], fb)[0])
        w_best = math.exp(-2.5 * max(0.0, alt - vab))
        ra, rb, rd = a >> 2, b >> 2, d >> 2
        w_low = 1.0 if rd <= min(ra, rb) else 0.12
        pb = (self.disc_best + 1.0) / (self.disc_n + 2.0)
        pl = (self.disc_low + 1.0) / (self.disc_n + 2.0)
        w = 0.08 + 0.92 * (pb * w_best + pl * w_low) / (pb + pl)
        self.dw_cache[key] = w
        return w

    # ----- postflop equity of our kept pair vs the weighted posterior
    def post_equity(self, mine, board, acts, budget):
        t0 = time.perf_counter()
        dead = set(mine) | set(board) | {self.my_disc, self.opp_disc}
        unseen = [c for c in range(52) if c not in dead]
        rng = self.rng
        ms = evaluate(mine + board)
        nb = len(board)
        num = den = 0.0
        draw_mass = 0.0
        strong_mass = 0.0
        cont_w = {}
        n = 0
        kmax = 260
        while n < kmax:
            if n >= 30 and time.perf_counter() - t0 > budget:
                break
            n += 1
            pair = rng.sample(unseen, 2)
            v, dr = vstrength(pair, board)
            w = self.disc_weight(tuple(pair)) * self.act_weight(v, acts)
            if w <= 1e-6:
                continue
            if nb == 5:
                so = evaluate(pair + board)
                r = 1.0 if ms > so else (0.5 if ms == so else 0.0)
            else:
                rest = [c for c in unseen if c != pair[0] and c != pair[1]]
                r = 0.0
                for _ in range(3):
                    rv = rng.choice(rest)
                    b5 = board + [rv]
                    a_ = evaluate(mine + b5)
                    o_ = evaluate(pair + b5)
                    r += 1.0 if a_ > o_ else (0.5 if a_ == o_ else 0.0)
                r /= 3.0
            num += w * r
            den += w
            if dr > 0:
                draw_mass += w
            if v >= 1.5:
                strong_mass += w
            cont_w[len(cont_w)] = (w, v)
        if den <= 0:
            return 0.5, 0.0, 0.0, []
        return num / den, draw_mass / den, strong_mass / den, list(cont_w.values())

    def fold_est(self, samples, frac):
        """Expected fold probability vs a bet of `frac` pot: range-based blended with observed."""
        if not samples:
            return self.fold_rate()
        vc = 0.9 + 0.9 * min(frac, 1.5)
        tot = sum(w for w, _ in samples)
        f = sum(w for w, v in samples if v < vc) / max(tot, 1e-9)
        return 0.5 * f + 0.5 * self.fold_rate()

    # ----- flop: equities of the three discard options vs sampled 3-card opp hands
    def flop_equities(self, hand3, board, acts, budget):
        t0 = time.perf_counter()
        dead = set(hand3) | set(board)
        unseen = [c for c in range(52) if c not in dead]
        rng = self.rng
        opts = []
        for i in range(3):
            opts.append([hand3[j] for j in range(3) if j != i])
        num = [0.0, 0.0, 0.0]
        den = 0.0
        draw_mass = strong_mass = 0.0
        samples = []
        n = 0
        while n < 220:
            if n >= 24 and time.perf_counter() - t0 > budget:
                break
            n += 1
            o3 = rng.sample(unseen, 3)
            vs = []
            for i, j in ((1, 2), (0, 2), (0, 1)):
                vs.append(vstrength([o3[i], o3[j]], board))
            bi = 0
            if vs[1][0] > vs[bi][0]:
                bi = 1
            if vs[2][0] > vs[bi][0]:
                bi = 2
            if rng.random() < 0.1:
                bi = rng.randrange(3)
            vbest = vs[bi][0]
            w = self.act_weight(vbest, acts, flop_only=True)
            if w <= 1e-6:
                continue
            okeep = [o3[j] for j in range(3) if j != bi]
            rest = [c for c in unseen if c not in o3]
            rv = rng.sample(rest, 2)
            b5 = board + rv
            so = evaluate(okeep + b5)
            for i in range(3):
                sm = evaluate(opts[i] + b5)
                num[i] += w * (1.0 if sm > so else (0.5 if sm == so else 0.0))
            den += w
            if vs[bi][1] > 0:
                draw_mass += w
            if vbest >= 1.5:
                strong_mass += w
            samples.append((w, vbest))
        if den <= 0:
            return [0.5, 0.5, 0.5], 0.0, 0.0, []
        return [x / den for x in num], draw_mass / den, strong_mass / den, samples

    # ----- sizing
    @staticmethod
    def clamp_raise(rq, to):
        mn = rq.get("min_raise") or 0
        mx = rq.get("max_raise") or 0
        to = int(round(to))
        if mx and to >= 0.72 * mx:
            to = mx
        return max(mn, min(mx, to)) if mx else to

    def mk_raise(self, rq, frac):
        pot = rq["pot"]
        c = rq["to_call"]
        to = rq["opp_bet"] + frac * (pot + c)
        return {"type": "action", "action": "raise", "amount": self.clamp_raise(rq, to)}

    # ----- decisions
    def act(self, rq):
        legal = rq.get("legal_actions", [])
        street = rq.get("street")
        self.time_left = rq.get("time_left_ms", 60000) / 1000.0
        if street == "preflop":
            return self.act_preflop(rq, legal)
        return self.act_post(rq, legal)

    def passive(self, legal):
        if "check" in legal:
            return {"type": "action", "action": "check"}
        if "call" in legal:
            return {"type": "action", "action": "call"}
        return {"type": "action", "action": "fold"}

    def act_preflop(self, rq, legal):
        rng = self.rng
        e = pf_equity(self.hole3)
        c = rq["to_call"]
        ob = rq["opp_bet"]
        can_raise = "raise" in legal
        r = rng.random()
        if ob <= 2 and self.seat == "button" and c > 0:         # SB, unopened
            if can_raise and ((e >= 0.545 and r < 0.9) or (e >= 0.47 and r < 0.07)):
                return {"type": "action", "action": "raise",
                        "amount": self.clamp_raise(rq, rng.choice((5, 6, 6, 7)))}
            return {"type": "action", "action": "call"}
        if c == 0:                                              # BB option after a limp
            if can_raise and ((e >= 0.57 and r < 0.85) or (0.48 <= e < 0.57 and r < 0.10)):
                return {"type": "action", "action": "raise",
                        "amount": self.clamp_raise(rq, rng.choice((6, 7, 8)))}
            return self.passive(legal)
        # facing a raise
        q = min(1.0, max(0.2, self.pfr()))
        ea = e - 0.17 * (1.0 - q)
        pot = rq["pot"]
        req = c / float(pot + c)
        n_raised = 4 - rq.get("raises_left", 3)
        if can_raise and ea >= 0.64 + 0.03 * max(0, n_raised - 2) and r < 0.85:
            size = 3.0 if n_raised <= 2 else 2.3
            to = max(ob * size, rq["min_raise"])
            if ea >= 0.74 and n_raised >= 3:
                to = rq["max_raise"]
            return {"type": "action", "action": "raise", "amount": self.clamp_raise(rq, to)}
        if can_raise and n_raised <= 2 and 0.46 <= e <= 0.56 and r < 0.05:
            return {"type": "action", "action": "raise",
                    "amount": self.clamp_raise(rq, ob * 3.0)}
        if ea >= req + 0.06:
            return {"type": "action", "action": "call"}
        if "fold" in legal:
            return {"type": "action", "action": "fold"}
        return self.passive(legal)

    def act_post(self, rq, legal):
        rng = self.rng
        board = [card(x) for x in rq["board"]]
        street = {"flop": 1, "turn": 2, "river": 3}.get(rq["street"], 1)
        acts, _mine = self.parse_history(rq.get("history", []))
        budget = self.budget()
        if street == 1 and len(self.hole3) == 3 and not self.kept:
            self.board_flop = board[:3]
            eqs, dm, sm_, samples = self.flop_equities(self.hole3, board, acts, budget)
            e = max(eqs)
            best = [self.hole3[j] for j in range(3) if j != eqs.index(max(eqs))]
        else:
            mine = self.kept if self.kept else self.hole3[:2]
            e, dm, sm_, samples = self.post_equity(mine, board, acts, budget)
            best = mine
        my_draw = 0.0
        if street < 3:
            try:
                my_draw = vstrength(best, board)[1]
            except Exception:
                my_draw = 0.0
        return self.decide_post(rq, legal, street, e, dm, samples, my_draw, rng)

    def decide_post(self, rq, legal, street, e, dm, samples, my_draw, rng):
        pot = rq["pot"]
        c = rq["to_call"]
        can_raise = "raise" in legal
        station = self.call_rate() > 0.68
        last = street == 3
        if c == 0:
            if not can_raise:
                return self.passive(legal)
            hi = 0.68 - (0.03 if station else 0.0)
            r = rng.random()
            if e >= hi:
                if e > 0.9 and street < 3 and r < 0.12:
                    return self.passive(legal)                    # occasional slowplay
                if r < 0.94:
                    frac = 0.60 if e < 0.82 else 0.78
                    if station:
                        frac += 0.10
                    return self.mk_raise(rq, frac)
                return self.passive(legal)
            if e >= 0.55:
                if r < (0.75 if station else 0.55):
                    return self.mk_raise(rq, 0.45)
                return self.passive(legal)
            if e >= 0.46:
                if r < (0.35 if station else 0.18):
                    return self.mk_raise(rq, 0.33)
                return self.passive(legal)
            if e < 0.42 and not station:
                f = self.fold_est(samples, 0.6)
                if last:
                    p = 0.5 * max(0.0, f - 0.30) * 2.0
                else:
                    p = 0.10 + 0.40 * (1.0 - dm) * max(0.0, f - 0.25) * 2.0
                    p += 0.25 * min(1.0, my_draw * 2.0)
                if f > 0.38 and r < min(0.5, p):
                    return self.mk_raise(rq, 0.60)
            return self.passive(legal)
        # facing a bet
        req = c / float(pot + c)
        margin = 0.02 if last else 0.045
        if req < 0.25:
            margin -= 0.02
        r = rng.random()
        if can_raise and e >= 0.80 and r < 0.75:
            return self.mk_raise(rq, 0.9)
        if can_raise and e >= 0.70 and r < 0.15:
            return self.mk_raise(rq, 0.8)
        if e >= req + margin:
            return {"type": "action", "action": "call"}
        if can_raise and not station and street < 3 and my_draw > 0.35 and e >= 0.28 and r < 0.18:
            return self.mk_raise(rq, 0.9)                          # semi-bluff raise
        if can_raise and not station and e < 0.30 and r < 0.04 and self.fold_est(samples, 0.9) > 0.5:
            return self.mk_raise(rq, 0.9)
        if "fold" in legal:
            return {"type": "action", "action": "fold"}
        return self.passive(legal)

    # ----- discard
    def act_discard(self, rq):
        self.time_left = rq.get("time_left_ms", 60000) / 1000.0
        hole = [card(x) for x in rq["hole_cards"]]
        board = [card(x) for x in rq["board"]]
        self.hole3 = hole
        self.board_flop = board[:3]
        acts = getattr(self, "_last_acts", [])
        budget = min(0.060, self.budget() * 1.6)
        eqs, _dm, _sm, _s = self.flop_equities(hole, board, acts, budget)
        order = sorted(range(3), key=lambda i: -eqs[i])
        i = order[0]
        # concealment tie-break: among near-equal options avoid always discarding the lowest card
        if eqs[order[0]] - eqs[order[1]] < 0.006 and self.rng.random() < 0.35:
            i = order[1]
        return {"type": "discard", "card": cstr(hole[i])}

    # ----- messages
    def on_hand_result(self, msg):
        try:
            hist = msg.get("history") or []
            opp_hole = msg.get("opp_hole_cards")
            opp_disc = msg.get("opp_discard")
            board = [card(x) for x in (msg.get("board") or [])]
            # response stats (our bets/raises -> opp reply)
            last_me_raise = None
            for e in hist:
                st = e.get("street")
                if e.get("actor") == "opp" and st == "preflop":
                    if e.get("action") == "raise":
                        self.pf_raise += 1
                    else:
                        self.pf_other += 1
                if st in ("flop", "turn", "river"):
                    if e.get("actor") == "me" and e.get("action") == "raise":
                        last_me_raise = st
                    elif e.get("actor") == "opp" and last_me_raise == st:
                        a = e.get("action")
                        if a == "fold":
                            self.resp_fold += 1
                        elif a == "call":
                            self.resp_call += 1
                        elif a == "raise":
                            self.resp_raise += 1
                        last_me_raise = None
                    elif e.get("actor") == "opp":
                        last_me_raise = None
            # opponent's discard behaviour, when its 3 cards are visible
            if opp_hole and opp_disc and len(board) >= 3:
                d = card(opp_disc)
                k = [card(x) for x in opp_hole]
                tri = [k[0], k[1], d]
                fb = board[:3]
                vs = [vstrength([tri[1], tri[2]], fb)[0], vstrength([tri[0], tri[2]], fb)[0],
                      vstrength([tri[0], tri[1]], fb)[0]]
                self.disc_n += 1
                if vs[2] >= max(vs) - 1e-9:
                    self.disc_best += 1
                if (d >> 2) <= min(k[0] >> 2, k[1] >> 2):
                    self.disc_low += 1
                if len(board) == 5:
                    vf = vstrength(k, board)[0]
                    aggressive = any(e.get("actor") == "opp" and e.get("action") == "raise"
                                     and e.get("street") in ("turn", "river") for e in hist)
                    if aggressive:
                        if vf >= 1.3:
                            self.val_cnt += 1
                        else:
                            self.bluff_cnt += 1
        except Exception as ex:
            print("hand_result err", ex, file=sys.stderr)

    def handle(self, msg):
        t = msg.get("type")
        if t == "init":
            self.total_hands = int(msg.get("total_hands", 400))
            self.bank_ms = float(msg.get("time_bank_ms", 60000))
            self.time_left = self.bank_ms / 1000.0
            return None
        if t == "new_hand":
            self.hand_no += 1
            self.seat = msg.get("seat", "button")
            self.hole3 = [card(x) for x in msg.get("hole_cards", [])]
            self.kept = []
            self.my_disc = self.opp_disc = None
            self.board_flop = []
            self.dw_cache = {}
            self._last_acts = []
            return None
        if t == "action_request":
            try:
                out = self.act(msg)
                if msg.get("street") == "flop":
                    self._last_acts = self.parse_history(msg.get("history", []))[0]
                return out
            except Exception as ex:
                print("act err", repr(ex), file=sys.stderr)
                return self.passive(msg.get("legal_actions", []))
        if t == "discard_request":
            try:
                return self.act_discard(msg)
            except Exception as ex:
                print("discard err", repr(ex), file=sys.stderr)
                try:
                    cs = msg["hole_cards"]
                    return {"type": "discard", "card": min(cs, key=lambda x: RANKS.index(x[0]))}
                except Exception:
                    return {"type": "discard", "card": "2s"}
        if t == "discard_result":
            try:
                self.kept = [card(x) for x in msg["hole_cards"]]
                self.my_disc = card(msg["my_discard"])
                self.opp_disc = card(msg["opp_discard"])
            except Exception as ex:
                print("dr err", ex, file=sys.stderr)
            return None
        if t == "hand_result":
            self.on_hand_result(msg)
            return None
        return None


def main():
    bot = Bot()
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        if msg.get("type") == "match_end":
            break
        try:
            reply = bot.handle(msg)
        except Exception as ex:
            print("handle err", repr(ex), file=sys.stderr)
            reply = None
            t = msg.get("type")
            if t == "action_request":
                reply = bot.passive(msg.get("legal_actions", []))
            elif t == "discard_request":
                reply = {"type": "discard", "card": (msg.get("hole_cards") or ["2s"])[0]}
        if reply is not None:
            out.write(json.dumps(reply, separators=(",", ":")) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
