#!/usr/bin/env python3.11
"""h3_adaptive: an opponent-modelling exploiter for heads-up Discard Hold'em.

Baseline: Monte-Carlo equity (own 7-card evaluator, discard-aware). On top of that it tracks
decayed opponent frequencies and shifts its play (bluff rate, value threshold, how tight it
treats the opponent's bets) as the sample supports it.  stdlib only; stdout = protocol only.
"""
import json
import random
import sys
import time

RANKS = "23456789TJQKA"
SUITS = "shdc"


def cd(s):
    return RANKS.index(s[0]) * 4 + SUITS.index(s[1])


# ----------------------------------------------------------------------------- evaluator
def _build_straight():
    t = [-1] * 8192
    for m in range(8192):
        for hi in range(12, 3, -1):
            w = 0
            for r in range(hi - 4, hi + 1):
                w |= 1 << r
            if m & w == w:
                t[m] = hi
                break
        else:
            if m & 0x100F == 0x100F:        # wheel A2345
                t[m] = 3
    return t


STRAIGHT = _build_straight()


def evalh(cards):
    """Score of the best 5-card hand among 5..7 card ints (rank = c >> 2, suit = c & 3)."""
    cnt = [0] * 13
    sc = [0, 0, 0, 0]
    mask = 0
    for c in cards:
        r = c >> 2
        cnt[r] += 1
        sc[c & 3] += 1
        mask |= 1 << r
    fs = -1
    for s in range(4):
        if sc[s] >= 5:
            fs = s
    if fs >= 0:
        fm = 0
        for c in cards:
            if c & 3 == fs:
                fm |= 1 << (c >> 2)
        h = STRAIGHT[fm]
        if h >= 0:
            return (8 << 20) | h
    q = []
    t = []
    p = []
    s1 = []
    for r in range(12, -1, -1):
        n = cnt[r]
        if n == 4:
            q.append(r)
        elif n == 3:
            t.append(r)
        elif n == 2:
            p.append(r)
        elif n == 1:
            s1.append(r)
    if q:
        rest = sorted(t + p + s1, reverse=True)
        vals = [q[0], rest[0]]
        cat = 7
    elif t and (len(t) > 1 or p):
        pr = max(t[1] if len(t) > 1 else -1, p[0] if p else -1)
        vals = [t[0], pr]
        cat = 6
    elif fs >= 0:
        vals = [r for r in range(12, -1, -1) if fm >> r & 1][:5]
        cat = 5
    elif STRAIGHT[mask] >= 0:
        vals = [STRAIGHT[mask]]
        cat = 4
    elif t:
        vals = [t[0]] + sorted(p + s1, reverse=True)[:2]
        cat = 3
    elif len(p) >= 2:
        rest = sorted(p[2:] + s1, reverse=True)
        vals = [p[0], p[1], rest[0]]
        cat = 2
    elif p:
        vals = [p[0]] + s1[:3]
        cat = 1
    else:
        vals = s1[:5]
        cat = 0
    v = cat
    for x in vals:
        v = (v << 4) | x
    for _ in range(5 - len(vals)):
        v <<= 4
    return v


def pick(cards3, flop):
    """The two cards a sensible player keeps out of three, given the flop."""
    best = None
    bs = -1
    fsuit = [0, 0, 0, 0]
    for c in flop:
        fsuit[c & 3] += 1
    for i in range(3):
        k = [cards3[j] for j in range(3) if j != i]
        sc = evalh(k + flop) * 64 + (k[0] >> 2) + (k[1] >> 2)
        if (k[0] & 3) == (k[1] & 3) and fsuit[k[0] & 3] >= 2:
            sc += 30
        if sc > bs:
            bs = sc
            best = k
    return best


def has_draw(hole2, board):
    """Four to a flush or four in a five-rank window using at least one hole card."""
    if len(board) >= 5:
        return False
    sc = [0, 0, 0, 0]
    for c in hole2 + board:
        sc[c & 3] += 1
    for s in range(4):
        if sc[s] >= 4 and any((c & 3) == s for c in hole2):
            return True
    hm = 0
    for c in hole2:
        hm |= 1 << (c >> 2)
    m = hm
    for c in board:
        m |= 1 << (c >> 2)
    for lo in range(-1, 9):
        w = 0
        for r in range(lo, lo + 5):
            w |= 1 << (12 if r == -1 else r)
        if bin(m & w).count("1") >= 4 and (hm & w):
            return True
    return False


# ----------------------------------------------------------------------------- opponent stats
class Stats:
    """Decayed [numerator, denominator] counters; every counter has a prior."""
    PRIORS = {
        "fold_b": (0.35, 6), "raise_b": (0.12, 6), "fold_r": (0.40, 5),
        "bet_f": (0.45, 5), "bet_t": (0.45, 5), "bet_r": (0.40, 5),
        "pf_fold": (0.35, 5), "pf_raise": (0.35, 5),
        "bet_pct": (0.66, 4), "call_pct": (0.50, 4), "disc_high": (0.10, 4),
    }

    def __init__(self):
        self.c = {k: [0.0, 0.0] for k in self.PRIORS}

    def decay(self, d=0.985):
        for v in self.c.values():
            v[0] *= d
            v[1] *= d

    def add(self, k, num, den=1.0):
        self.c[k][0] += num
        self.c[k][1] += den

    def get(self, k):
        p, w = self.PRIORS[k]
        n, d = self.c[k]
        return (n + p * w) / (d + w)

    def n(self, k):
        return self.c[k][1]


# ----------------------------------------------------------------------------- the bot
class Bot:
    def __init__(self):
        self.st = Stats()
        self.total_hands = 200
        self.bank_ms = 30000.0
        self.time_left = 30000.0
        self.hands_seen = 0
        self.cost = 0.0001          # seconds per MC sample (EMA)
        self.reset_hand()

    def reset_hand(self):
        self.hole = []
        self.my_disc = None
        self.opp_disc = None
        self.button = False

    # ---------------------------------------------------------------- sampling budget
    def n_samples(self, hi, lo=20):
        hands_left = max(1, self.total_hands - self.hands_seen + 1)
        budget = self.time_left / 1000.0 / (hands_left * 5.5) * 0.6
        budget = min(budget, 0.016)
        n = int(budget / max(self.cost, 2e-5))
        return max(lo, min(hi, n))

    # ---------------------------------------------------------------- equity
    def equity(self, hole, board, k, n, rej=0.0):
        known = set(hole) | set(board)
        if self.my_disc is not None:
            known.add(self.my_disc)
        if self.opp_disc is not None:
            known.add(self.opp_disc)
        unseen = [c for c in range(52) if c not in known]
        pre = len(hole) == 3
        no = 3 if pre else 2
        nb = 5 - len(board)
        need = no + nb
        od = self.opp_disc
        res = []
        t0 = time.perf_counter()
        tries = 0
        while len(res) < n and tries < n * 2:
            tries += 1
            s = random.sample(unseen, need)
            opp = s[:no]
            full = board + s[no:]
            if pre:
                flop = full[:3]
                me2 = pick(hole, flop)
                o2 = pick(opp, flop)
            else:
                me2 = hole
                o2 = opp
                if od is not None and rej > 0 and (od >> 2) > (o2[0] >> 2) and (od >> 2) > (o2[1] >> 2):
                    if random.random() < rej:
                        continue
            a = evalh(me2 + full)
            b = evalh(o2 + full)
            res.append((b, 1.0 if a > b else (0.5 if a == b else 0.0)))
        if not res:
            return 0.5
        self.cost = 0.7 * self.cost + 0.3 * ((time.perf_counter() - t0) / max(1, tries))
        if k <= 0.05:
            return sum(r[1] for r in res) / len(res)
        res.sort(key=lambda x: x[0])
        m = len(res)
        tw = 0.0
        tv = 0.0
        for i, (_, v) in enumerate(res):
            w = ((i + 0.5) / m) ** k
            tw += w
            tv += w * v
        return tv / tw

    def pct_vs_random(self, hole2, board, n=50):
        """Share of random 2-card hands our hole2 beats on this (>=3 card) board."""
        known = set(hole2) | set(board)
        unseen = [c for c in range(52) if c not in known]
        me = evalh(hole2 + board) if len(board) >= 3 else 0
        w = 0.0
        for _ in range(n):
            o = random.sample(unseen, 2)
            b = evalh(o + board)
            w += 1.0 if me > b else (0.5 if me == b else 0.0)
        return w / n

    # ---------------------------------------------------------------- discard
    def discard(self, req):
        hole = [cd(c) for c in req["hole_cards"]]
        board = [cd(c) for c in req["board"]]
        self.hole = hole
        known = set(hole) | set(board)
        unseen = [c for c in range(52) if c not in known]
        n = self.n_samples(70, 12)
        sc = [0.0, 0.0, 0.0]
        t0 = time.perf_counter()
        for _ in range(n):
            s = random.sample(unseen, 5)
            opp = s[:3]
            full = board + s[3:]
            o2 = pick(opp, board[:3])
            b = evalh(o2 + full)
            for i in range(3):
                k = [hole[j] for j in range(3) if j != i]
                a = evalh(k + full)
                sc[i] += 1.0 if a > b else (0.5 if a == b else 0.0)
        self.cost = 0.7 * self.cost + 0.3 * ((time.perf_counter() - t0) / max(1, n) / 3.0)
        i = max(range(3), key=lambda j: (sc[j], -(hole[j] >> 2)))
        return req["hole_cards"][i]

    # ---------------------------------------------------------------- betting
    def act(self, req):
        legal = set(req["legal_actions"])
        street = req["street"]
        board = [cd(c) for c in req["board"]]
        pot = req["pot"]
        ob = req["opp_bet"]
        mb = req["my_bet"]
        to_call = req["to_call"]
        minr = req.get("min_raise") or 0
        maxr = req.get("max_raise") or 0
        raises_left = req.get("raises_left", 0)
        hist = [h for h in req.get("history", []) if h["street"] == street]
        opp_raises = sum(1 for h in hist if h["actor"] == "opp" and h["action"] == "raise")
        my_raises = sum(1 for h in hist if h["actor"] == "me" and h["action"] == "raise")
        S = self.st

        # how much to believe the opponent's aggression
        k = 0.0
        if to_call > 0 and (opp_raises > 0 or street != "preflop"):
            kb = max(0.0, (S.get("bet_pct") - 0.5) * 6.0)
            r = to_call / max(1.0, pot - to_call)
            k = kb * min(1.6, max(0.7, 0.7 + 0.6 * r))
            if opp_raises >= 2:
                k *= 1.3
            if street == "preflop":
                k *= 0.6
        rej = 0.6 * (1.0 - S.get("disc_high") * 2.0) if len(self.hole) == 2 else 0.0
        rej = max(0.0, min(0.6, rej))
        n = self.n_samples(130)
        e = self.equity(self.hole, board, k, n, rej)
        draw = len(self.hole) == 2 and has_draw(self.hole, board)

        fb = S.get("fold_b")
        callrate = 1.0 - fb
        ftr = S.get("fold_r")
        bet_rate = {"flop": S.get("bet_f"), "turn": S.get("bet_t"), "river": S.get("bet_r")}.get(street, 0.4)

        def raise_to(frac):
            rt = ob + int(frac * (pot + to_call))
            rt = max(rt, minr)
            if maxr and rt > maxr:
                rt = maxr
            if maxr and maxr - rt < 0.35 * (pot + to_call):
                rt = maxr
            return int(max(rt, minr)) if maxr >= minr else int(maxr)

        def do_raise(frac):
            if "raise" not in legal or maxr <= 0:
                return None
            return {"type": "action", "action": "raise", "amount": raise_to(frac)}

        def passive():
            if "check" in legal:
                return {"type": "action", "action": "check"}
            return {"type": "action", "action": "call"}

        rnd = random.random()
        # ------------------------------------------------ facing a bet / raise (or blinds)
        if to_call > 0:
            odds = to_call / (pot + to_call)
            if street == "preflop" and opp_raises == 0 and not hist:
                # small blind facing the big blind, or big blind facing a limp-free open
                pass
            marg = 0.02 if street == "preflop" else 0.03
            if street == "preflop" and self.button and opp_raises == 0 and my_raises == 0:
                # SB first action: open wide, more so against folders
                pf_f = S.get("pf_fold")
                thr = 0.53 - 0.12 * (pf_f - 0.35)
                if e > thr and rnd < 0.85:
                    a = do_raise(1.3 if pf_f > 0.5 else 1.0)
                    if a:
                        return a
                if e > 0.30:
                    return {"type": "action", "action": "call"}
                return {"type": "action", "action": "fold"}
            if raises_left > 0 and "raise" in legal:
                vthr = 0.70 - 0.05 * max(0.0, 0.3 - k)
                if e > vthr and rnd < 0.8:
                    return do_raise(0.9 if e > 0.85 else 0.7)
                if e > 0.9:
                    return do_raise(1.0)
                if street != "river" and draw and 0.28 < e < 0.55 and e > odds - 0.1:
                    p = 0.10 + 0.5 * max(0.0, bet_rate - 0.4) + 0.5 * max(0.0, ftr - 0.4)
                    if rnd < min(0.4, p):
                        return do_raise(0.75)
                if e < 0.35 and ftr > 0.55 and opp_raises == 0 and rnd < 0.07 * (ftr - 0.45) * 10:
                    return do_raise(0.8)
            if e > odds + marg:
                return {"type": "action", "action": "call"}
            # a little defence against frequent weak bettors
            if e > odds - 0.04 and bet_rate > 0.55 and S.get("bet_pct") < 0.62 and rnd < 0.4:
                return {"type": "action", "action": "call"}
            return {"type": "action", "action": "fold"}

        # ------------------------------------------------ nothing to call: bet or check
        if "raise" not in legal or raises_left <= 0:
            return passive()
        bluff_p = min(0.5, max(0.02, 0.06 + 1.1 * (fb - 0.35)))
        vthr = min(0.66, max(0.52, 0.60 - 0.25 * (callrate - 0.6)))
        if street == "preflop":
            vthr = max(0.55, vthr)
        if e > vthr:
            if e > 0.85 and street == "flop" and rnd < 0.2:
                return passive()
            if rnd < 0.9:
                if e > 0.85:
                    f = 0.9 if callrate > 0.6 else 0.7
                elif e > 0.72:
                    f = 1.0 if callrate > 0.7 else 0.65
                else:
                    f = 0.5
                return do_raise(f)
            return passive()
        cap = 0.30 if street == "river" else 0.42
        if e < cap:
            p = bluff_p * (1.5 if draw else 1.0) * (0.8 if street == "river" else 1.0)
            if street == "preflop":
                p *= 0.4
            if random.random() < p:
                return do_raise(0.55 if fb > 0.5 else 0.7)
        return passive()

    # ---------------------------------------------------------------- learning
    def learn(self, msg):
        S = self.st
        S.decay()
        hist = msg.get("history") or []
        bets = {"me": 1 if self.button else 2, "opp": 2 if self.button else 1}
        street = None
        opp_aggr = {}
        my_aggr = {}
        opp_bet_streets = []
        opp_call_streets = []
        for a in hist:
            s = a["street"]
            if s != street:
                street = s
                bets = {"me": 1 if self.button else 2, "opp": 2 if self.button else 1} if s == "preflop" else {"me": 0, "opp": 0}
            who = a["actor"]
            act = a["action"]
            amt = a.get("amount")
            other = "me" if who == "opp" else "opp"
            if who == "opp":
                to_call = bets["me"] - bets["opp"]
                if s == "preflop":
                    if to_call > 0 and not my_aggr.get(s) and not opp_aggr.get(s):
                        S.add("pf_raise", 1.0 if act == "raise" else 0.0)
                    elif to_call > 0 and my_aggr.get(s):
                        S.add("pf_fold", 1.0 if act == "fold" else 0.0)
                    if act == "raise":
                        opp_bet_streets.append(s)
                else:
                    key = {"flop": "bet_f", "turn": "bet_t", "river": "bet_r"}[s]
                    if to_call == 0:
                        S.add(key, 1.0 if act == "raise" else 0.0)
                    elif opp_aggr.get(s):
                        S.add("fold_r", 1.0 if act == "fold" else 0.0)
                    else:
                        S.add("fold_b", 1.0 if act == "fold" else 0.0)
                        S.add("raise_b", 1.0 if act == "raise" else 0.0)
                    if act == "raise":
                        opp_bet_streets.append(s)
                    elif act == "call":
                        opp_call_streets.append(s)
                if act == "raise":
                    opp_aggr[s] = True
            else:
                if act == "raise":
                    my_aggr[s] = True
            if act in ("call", "raise") and amt is not None:
                bets[who] = amt
        # showdown strength of the opponent's bets and calls, and discard sanity
        oh = msg.get("opp_hole_cards")
        board = [cd(c) for c in msg.get("board") or []]
        if oh and len(oh) == 2 and len(board) >= 3:
            try:
                o2 = [cd(c) for c in oh]
                n_post = [s for s in opp_bet_streets if s != "preflop"]
                n_call = [s for s in opp_call_streets if s != "preflop"]
                if n_post or n_call:
                    p = self.pct_vs_random(o2, board)
                    if n_post:
                        S.add("bet_pct", p, 1.0)
                    if n_call:
                        S.add("call_pct", p, 1.0)
                od = msg.get("opp_discard")
                if od:
                    d = cd(od)
                    S.add("disc_high", 1.0 if (d >> 2) > max(o2[0] >> 2, o2[1] >> 2) else 0.0)
            except Exception:
                pass

    # ---------------------------------------------------------------- fallbacks
    @staticmethod
    def safe_action(req):
        legal = req.get("legal_actions", [])
        if "check" in legal:
            return {"type": "action", "action": "check"}
        if req.get("to_call", 0) <= 2 and "call" in legal:
            return {"type": "action", "action": "call"}
        return {"type": "action", "action": "fold"}

    @staticmethod
    def sanitize(rep, req):
        legal = req.get("legal_actions", [])
        a = rep.get("action")
        if a not in legal:
            return Bot.safe_action(req)
        if a == "raise":
            lo = req.get("min_raise") or 0
            hi = req.get("max_raise") or 0
            amt = int(rep.get("amount", lo))
            amt = max(lo, min(hi, amt))
            if hi < lo:
                amt = hi
            return {"type": "action", "action": "raise", "amount": amt}
        return {"type": "action", "action": a}


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    bot = Bot()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        t = msg.get("type")
        try:
            if t == "init":
                bot.total_hands = int(msg.get("total_hands", 200))
                bot.bank_ms = float(msg.get("time_bank_ms", 30000))
                bot.time_left = bot.bank_ms
            elif t == "new_hand":
                bot.reset_hand()
                bot.hands_seen += 1
                bot.hole = [cd(c) for c in msg["hole_cards"]]
                bot.button = msg.get("seat") == "button"
            elif t == "action_request":
                if "time_left_ms" in msg:
                    bot.time_left = float(msg["time_left_ms"])
                try:
                    rep = bot.sanitize(bot.act(msg), msg)
                except Exception as ex:
                    sys.stderr.write("act error: %r\n" % (ex,))
                    rep = bot.safe_action(msg)
                send(rep)
            elif t == "discard_request":
                if "time_left_ms" in msg:
                    bot.time_left = float(msg["time_left_ms"])
                try:
                    card = bot.discard(msg)
                except Exception as ex:
                    sys.stderr.write("discard error: %r\n" % (ex,))
                    card = min(msg["hole_cards"], key=lambda c: RANKS.index(c[0]))
                send({"type": "discard", "card": card})
            elif t == "discard_result":
                bot.hole = [cd(c) for c in msg["hole_cards"]]
                bot.my_disc = cd(msg["my_discard"])
                bot.opp_disc = cd(msg["opp_discard"])
            elif t == "hand_result":
                bot.learn(msg)
            elif t == "match_end":
                break
        except Exception as ex:
            sys.stderr.write("error on %s: %r\n" % (t, ex))


if __name__ == "__main__":
    main()
