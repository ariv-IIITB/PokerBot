"""h5_smallball: position-driven small-ball bot for heads-up Discard Hold'em.

Single file, stdlib only. JSON lines over stdin/stdout; debug to stderr only.
Style: use the last-to-act edge postflop, small frequent bets (25-40% pot), probes and
delayed c-bets when checked to, floats with draws in position, folds to big pressure with
weak hands, keeps pots small out of position. Equity by Monte Carlo.
"""
import sys
import json
import time
import random

RANKS = "23456789TJQKA"
SUITS = "shdc"
RNG = random.Random()

# ----------------------------------------------------------------------------- evaluator
# card int = rank*4 + suit ; rank 0..12 (2..A)


def _build_tables():
    straight = [-1] * 8192
    top5 = [0] * 8192
    for m in range(8192):
        for h in range(12, 3, -1):
            need = 31 << (h - 4)
            if m & need == need:
                straight[m] = h
                break
        else:
            if m & 0x100F == 0x100F:        # A,2,3,4,5 wheel
                straight[m] = 3
        v, n = 0, 0
        for r in range(12, -1, -1):
            if m >> r & 1:
                v = v << 4 | r
                n += 1
                if n == 5:
                    break
        top5[m] = v if n == 5 else 0
    return straight, top5


STR, TOP5 = _build_tables()


def ev(cs):
    """Best-5 strength of 5..7 cards (higher is better)."""
    rc = [0] * 13
    sm = [0, 0, 0, 0]
    sn = [0, 0, 0, 0]
    mask = 0
    for c in cs:
        r = c >> 2
        s = c & 3
        rc[r] += 1
        sm[s] |= 1 << r
        sn[s] += 1
        mask |= 1 << r
    fm = 0
    for s in range(4):
        if sn[s] >= 5:
            fm = sm[s]
            h = STR[fm]
            if h >= 0:
                return (8 << 24) | h
            break
    quad = -1
    trips = []
    pairs = []
    for r in range(12, -1, -1):
        n = rc[r]
        if n == 4:
            quad = r
        elif n == 3:
            trips.append(r)
        elif n == 2:
            pairs.append(r)
    if quad >= 0:
        k = -1
        for r in range(12, -1, -1):
            if rc[r] and r != quad:
                k = r
                break
        return (7 << 24) | quad << 4 | k
    if trips and (len(trips) > 1 or pairs):
        p = pairs[0] if pairs else -1
        if len(trips) > 1 and trips[1] > p:
            p = trips[1]
        return (6 << 24) | trips[0] << 4 | p
    if fm:
        return (5 << 24) | TOP5[fm]
    h = STR[mask]
    if h >= 0:
        return (4 << 24) | h
    if trips:
        t = trips[0]
        v = t
        n = 0
        for r in range(12, -1, -1):
            if rc[r] and r != t:
                v = v << 4 | r
                n += 1
                if n == 2:
                    break
        return (3 << 24) | v
    if len(pairs) >= 2:
        a, b = pairs[0], pairs[1]
        k = 0
        for r in range(12, -1, -1):
            if rc[r] and r != a and r != b:
                k = r
                break
        return (2 << 24) | a << 8 | b << 4 | k
    if pairs:
        p = pairs[0]
        v = p
        n = 0
        for r in range(12, -1, -1):
            if rc[r] and r != p:
                v = v << 4 | r
                n += 1
                if n == 3:
                    break
        return (1 << 24) | v
    return TOP5[mask]


def pc(s):
    return RANKS.index(s[0]) * 4 + SUITS.index(s[1])


def cstr(c):
    return RANKS[c >> 2] + SUITS[c & 3]


# ----------------------------------------------------------------------------- preflop heuristic

_HP = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 10.0]


def chen2(a, b):
    ra, rb = a >> 2, b >> 2
    hi, lo = max(ra, rb), min(ra, rb)
    s = _HP[hi]
    if hi == lo:
        return max(5.0, s * 2)
    if a & 3 == b & 3:
        s += 2
    gap = hi - lo - 1
    s -= (0, 1, 2, 4, 5)[min(gap, 4)]
    if gap <= 1 and hi < 10:
        s += 1
    return s


def pre_score(h3):
    a, b, c = h3
    subs = (chen2(a, b), chen2(a, c), chen2(b, c))
    best = max(subs)
    extra = sum(1 for x in subs if x >= 7.0) - 1
    s = best + 0.6 * max(0, extra)
    # all three one suit / connected flexibility
    if a & 3 == b & 3 == c & 3:
        s += 1.0
    return s


# ----------------------------------------------------------------------------- equity (Monte Carlo)

FULL = list(range(52))


def mc_post(hole, board, dead, n, opp_disc=None):
    """Equity of kept 2 cards `hole` vs an opponent who kept 2 unseen cards (post-discard)."""
    seen = set(hole) | set(board) | set(dead)
    unseen = [c for c in FULL if c not in seen]
    need = 5 - len(board)
    flop = board[:3]
    d = opp_disc
    wins = 0.0
    done = 0
    attempts = 0
    sample = RNG.sample
    rand = RNG.random
    while done < n and attempts < n * 3:
        attempts += 1
        s = sample(unseen, 2 + need)
        a, b = s[0], s[1]
        if d is not None and len(flop) == 3:
            k = ev(flop + [a, b])
            alt = max(ev(flop + [a, d]), ev(flop + [b, d]))
            if k < alt and rand() > 0.35:
                continue
        bd = board + s[2:]
        m = ev(bd + hole)
        o = ev(bd + [a, b])
        if m > o:
            wins += 1.0
        elif m == o:
            wins += 0.5
        done += 1
    return wins / done if done else 0.5


def mc_discard(h3, board, n):
    """Equity of each keep option on the flop (index = card discarded). Opp holds 3 unseen
    cards and keeps its best two by current made hand."""
    seen = set(h3) | set(board)
    unseen = [c for c in FULL if c not in seen]
    opts = [[h3[1], h3[2]], [h3[0], h3[2]], [h3[0], h3[1]]]
    w = [0.0, 0.0, 0.0]
    sample = RNG.sample
    for _ in range(n):
        s = sample(unseen, 5)
        o3 = s[:3]
        run = s[3:]
        bd = board + run
        fb = board
        e1 = ev(fb + [o3[0], o3[1]])
        e2 = ev(fb + [o3[0], o3[2]])
        e3 = ev(fb + [o3[1], o3[2]])
        if e1 >= e2 and e1 >= e3:
            ok = (o3[0], o3[1])
        elif e2 >= e3:
            ok = (o3[0], o3[2])
        else:
            ok = (o3[1], o3[2])
        o = ev(bd + list(ok))
        for i in range(3):
            m = ev(bd + opts[i])
            if m > o:
                w[i] += 1.0
            elif m == o:
                w[i] += 0.5
    return [x / n for x in w]


def draw_bonus(keep, board):
    """Small bonus for keeping flush/straight draws (equity realisation), flop only."""
    if len(board) != 3:
        return 0.0
    cs = keep + board
    sn = [0] * 4
    for c in cs:
        sn[c & 3] += 1
    b = 0.0
    if max(sn) == 4 and any(sn[k & 3] == 4 for k in keep):
        b += 0.025
    mask = 0
    for c in cs:
        mask |= 1 << (c >> 2)
    best = 0
    for lo in range(-1, 9):
        w = 0
        for r in range(lo, lo + 5):
            rr = 12 if r < 0 else r
            if mask >> rr & 1:
                w += 1
        best = max(best, w)
    if best >= 4 and STR[mask] < 0:
        b += 0.015
    return b


# ----------------------------------------------------------------------------- bot state


class Bot:
    def __init__(self):
        self.total_hands = 400
        self.hand_id = 0
        self.seat = "button"
        self.hole = []
        self.board = []
        self.my_disc = None
        self.opp_disc = None
        self.hist_n = 0
        self.floated = False
        self.flop_eq = None
        self.lead_eq = None
        # opponent model
        self.opp_actions = 0
        self.opp_aggr = 0
        self.fold_faced = 0
        self.fold_cnt = 0
        self.opp_vpip_h = 0
        self.hands_seen = 0
        self.pre_raise_faced = 0
        self.pre_fold_to_raise = 0
        self.time_left = 30000.0

    # ---- helpers
    def ip(self):
        return self.seat == "button"

    def samples(self, base):
        tl = self.time_left
        left = max(1, self.total_hands - self.hand_id + 1)
        per_hand = tl / left
        if per_hand < 25:
            return max(12, base // 6)
        if per_hand < 60:
            return max(20, base // 2)
        return base

    def observe(self, hist):
        """Update opponent model from new history entries."""
        for i in range(self.hist_n, len(hist)):
            e = hist[i]
            if e.get("actor") != "opp":
                continue
            st = e.get("street")
            act = e.get("action")
            prev = hist[i - 1] if i > 0 else None
            faced = (prev is not None and prev.get("street") == st and prev.get("actor") == "me"
                     and prev.get("action") == "raise")
            if st == "preflop":
                if faced:
                    self.pre_raise_faced += 1
                    if act == "fold":
                        self.pre_fold_to_raise += 1
                continue
            self.opp_actions += 1
            if act == "raise":
                self.opp_aggr += 1
            if faced:
                self.fold_faced += 1
                if act == "fold":
                    self.fold_cnt += 1
        self.hist_n = len(hist)

    def fold_rate(self):
        return (self.fold_cnt + 2) / (self.fold_faced + 5)      # prior ~0.4

    def aggr_rate(self):
        return (self.opp_aggr + 1) / (self.opp_actions + 4)     # prior ~0.25

    # ---- messages
    def on_init(self, m):
        self.total_hands = int(m.get("total_hands", 400))
        self.time_left = float(m.get("time_bank_ms", 30000))

    def on_new_hand(self, m):
        self.hand_id = int(m.get("hand_id", self.hand_id + 1))
        self.seat = m.get("seat", "button")
        self.hole = [pc(c) for c in m["hole_cards"]]
        self.board = []
        self.my_disc = None
        self.opp_disc = None
        self.hist_n = 0
        self.floated = False
        self.flop_eq = None

    def on_discard_result(self, m):
        self.my_disc = pc(m["my_discard"])
        self.opp_disc = pc(m["opp_discard"])
        self.hole = [pc(c) for c in m["hole_cards"]]

    # ---- discard
    def discard(self, m):
        self.time_left = float(m.get("time_left_ms", self.time_left))
        h3 = [pc(c) for c in m["hole_cards"]]
        board = [pc(c) for c in m["board"]]
        eqs = mc_discard(h3, board, self.samples(110))
        best_i, best_v = 0, -1.0
        ip = self.ip()
        for i in range(3):
            keep = [h3[j] for j in range(3) if j != i]
            v = eqs[i] + draw_bonus(keep, board) * (1.0 if ip else 0.6)
            if v > best_v:
                best_v, best_i = v, i
        return {"type": "discard", "card": cstr(h3[best_i])}

    # ---- action
    def act(self, m):
        self.time_left = float(m.get("time_left_ms", self.time_left))
        legal = m["legal_actions"]
        self.observe(m.get("history", []))
        street = m["street"]
        board = [pc(c) for c in m["board"]]
        pot = int(m["pot"])
        my_bet = int(m["my_bet"])
        opp_bet = int(m["opp_bet"])
        to_call = int(m["to_call"])
        my_stack = int(m["my_stack"])
        can_raise = "raise" in legal
        rmin = int(m.get("min_raise", 0))
        rmax = int(m.get("max_raise", 0))
        hist = m.get("history", [])

        if street == "preflop":
            return self.preflop(m, legal, pot, my_bet, opp_bet, to_call, can_raise, rmin, rmax, hist)

        # equity
        if street == "flop" and self.my_disc is None:
            h3 = self.hole
            eqs = mc_discard(h3, board, self.samples(90))
            eq = max(eqs)
        else:
            dead = [self.my_disc, self.opp_disc]
            n = self.samples(150 if street != "river" else 220)
            eq = mc_post(self.hole, board, dead, n, self.opp_disc)

        ip = self.ip()
        # did the previous street go check-check? (weakness shown)
        weak = False
        order = ["preflop", "flop", "turn", "river"]
        pi = order.index(street) - 1
        if pi >= 1:
            ps = [e for e in hist if e.get("street") == order[pi]]
            weak = bool(ps) and all(e.get("action") == "check" for e in ps)

        if to_call > 0:
            return self.facing_bet(m, legal, eq, pot, to_call, opp_bet, my_bet, my_stack,
                                   can_raise, rmin, rmax, street, hist, ip)
        return self.checked_to(m, legal, eq, pot, my_stack, can_raise, rmin, rmax, street, ip, weak)

    # ---- bet sizing
    def size_to(self, frac, pot, opp_bet, rmin, rmax):
        amt = opp_bet + int(round(frac * (pot + (opp_bet))))
        amt = max(amt, rmin)
        return min(amt, rmax)

    def act_raise(self, amt, rmin, rmax):
        amt = int(max(rmin, min(rmax, amt)))
        return {"type": "action", "action": "raise", "amount": amt}

    def checked_to(self, m, legal, eq, pot, my_stack, can_raise, rmin, rmax, street, ip, weak):
        chk = {"type": "action", "action": "check"}
        if not can_raise:
            return chk
        r = RNG.random()
        fr = self.fold_rate()
        frac = RNG.choice((0.28, 0.33, 0.33, 0.4))
        if street == "river":
            frac += 0.07
        if ip:
            if eq >= 0.80:
                # value: bigger sometimes
                f = RNG.choice((0.4, 0.5, 0.66)) if street != "flop" else RNG.choice((0.33, 0.4, 0.5))
                return self.act_raise(self.size_to(f, pot, 0, rmin, rmax), rmin, rmax)
            if eq >= 0.58:
                if r < 0.85:
                    return self.act_raise(self.size_to(frac, pot, 0, rmin, rmax), rmin, rmax)
                return chk
            # probe / delayed c-bet / stab
            p = 0.0
            if eq >= 0.30:
                p = 0.55
            elif eq >= 0.15:
                p = 0.40
            else:
                p = 0.25
            if weak:
                p += 0.15
            if self.floated:
                p += 0.2
            p += (fr - 0.4) * 0.8                # exploit a folder, ease off a station
            if eq >= 0.45 and eq < 0.58:
                p = 0.50 + (fr - 0.4) * 0.5
            if street == "river" and eq < 0.35:
                p *= 0.7
            if r < max(0.05, min(0.85, p)):
                return self.act_raise(self.size_to(frac, pot, 0, rmin, rmax), rmin, rmax)
            return chk
        # out of position: keep the pot small
        if eq >= 0.85 and r < 0.35:
            return chk                            # occasional slowplay
        if eq >= 0.70:
            f = frac if street != "river" else 0.45
            return self.act_raise(self.size_to(f, pot, 0, rmin, rmax), rmin, rmax)
        if eq >= 0.60 and r < 0.55:
            return self.act_raise(self.size_to(frac, pot, 0, rmin, rmax), rmin, rmax)
        # probe: opp (IP) showed weakness last street by checking back
        if weak and eq >= 0.35 and r < 0.50 + (fr - 0.4) * 0.5:
            return self.act_raise(self.size_to(0.3, pot, 0, rmin, rmax), rmin, rmax)
        if street == "flop" and eq >= 0.45 and r < 0.18:
            return self.act_raise(self.size_to(0.3, pot, 0, rmin, rmax), rmin, rmax)
        return chk

    def facing_bet(self, m, legal, eq, pot, to_call, opp_bet, my_bet, my_stack, can_raise,
                   rmin, rmax, street, hist, ip):
        fold = {"type": "action", "action": "fold"}
        call = {"type": "action", "action": "call"}
        prior = pot - to_call
        bet_frac = to_call / max(1.0, float(prior))
        odds = to_call / float(pot + to_call)
        opp_raised = False
        mine_this = [e for e in hist if e.get("street") == street and e.get("actor") == "me"]
        if any(e.get("action") == "raise" for e in mine_this):
            opp_raised = True                       # they re-raised our bet
        agg = self.aggr_rate()
        shrink = min(0.16, 0.10 * bet_frac) * (1.0 - min(0.5, max(0.0, (agg - 0.3)) * 1.5))
        if opp_raised:
            shrink += 0.05
        adj = eq - shrink
        margin = 0.0 if ip else 0.03
        if bet_frac > 0.75:
            margin += 0.04                          # big pressure: need real hands
        # all-in-ish decisions need more
        commit = to_call / float(max(1, my_stack + to_call))
        if commit > 0.5:
            margin += 0.03
        r = RNG.random()
        # value raise
        if can_raise and not opp_raised:
            if adj >= 0.80:
                tgt = opp_bet + int(round(RNG.choice((0.75, 1.0, 1.25)) * (pot)))
                return self.act_raise(tgt, rmin, rmax)
            if adj >= 0.70 and r < 0.35:
                tgt = opp_bet + int(round(0.8 * pot))
                return self.act_raise(tgt, rmin, rmax)
            # in-position semi-bluff raise (rare, small-ball)
            if ip and street in ("flop", "turn") and 0.30 <= eq < 0.50 and bet_frac < 0.5 and r < 0.06:
                tgt = opp_bet + int(round(0.9 * pot))
                return self.act_raise(tgt, rmin, rmax)
        elif can_raise and adj >= 0.90 and r < 0.6:
            return self.act_raise(rmax if adj >= 0.95 else opp_bet + pot, rmin, rmax)
        if adj >= odds + margin:
            return call
        # float in position on the flop with draws/backdoors
        if ip and street == "flop" and bet_frac <= 0.6 and eq >= 0.30 and adj >= odds - 0.06:
            self.floated = True
            return call
        if ip and street == "turn" and bet_frac <= 0.45 and eq >= 0.34 and adj >= odds - 0.03 and r < 0.5:
            self.floated = True
            return call
        return fold

    # ---- preflop
    def preflop(self, m, legal, pot, my_bet, opp_bet, to_call, can_raise, rmin, rmax, hist):
        fold = {"type": "action", "action": "fold"}
        call = {"type": "action", "action": "call"}
        chk = {"type": "action", "action": "check"}
        s = pre_score(self.hole) + RNG.uniform(-0.4, 0.4)
        r = RNG.random()
        button = self.seat == "button"
        n_raises = sum(1 for e in hist if e.get("street") == "preflop" and e.get("action") == "raise")
        if "check" in legal:
            # BB facing a limp: iso-raise decent hands small, else check
            if can_raise and s >= 6.5 and r < 0.75:
                return self.act_raise(5, rmin, rmax)
            return chk
        # to_call > 0
        bb_in_hand = max(2, my_bet)
        if button and n_raises == 0:
            # first to act as SB: open small / complete / fold bottom
            if can_raise and s >= 5.2:
                return self.act_raise(5 if s >= 8 else 4 if r < 0.5 else 5, rmin, rmax)
            if s >= 3.5:
                return call
            return call if r < 0.45 else fold
        # facing a raise
        size = opp_bet
        if n_raises <= 1:
            # facing a single raise (or BB facing SB open): defend wide, 3-bet small
            need = 4.2 + 0.5 * max(0, size - 4)
            if not button:
                need -= 0.6                         # price from the BB
            if can_raise and s >= 10.0 and r < 0.8:
                return self.act_raise(size * 3, rmin, rmax)
            if can_raise and 7.5 <= s < 10.0 and r < 0.15:
                return self.act_raise(size * 3, rmin, rmax)
            if s >= need:
                return call
            return fold
        # 3-bet or more
        if can_raise and s >= 13.5:
            return self.act_raise(int(opp_bet * 2.3), rmin, rmax)
        if s >= 9.5 + 0.2 * max(0, size - 8):
            return call
        return fold


# ----------------------------------------------------------------------------- main loop


def safe_action(m):
    legal = m.get("legal_actions", [])
    if "check" in legal:
        return {"type": "action", "action": "check"}
    if "call" in legal and int(m.get("to_call", 0)) <= max(2, int(m.get("pot", 0)) // 4):
        return {"type": "action", "action": "call"}
    if "fold" in legal:
        return {"type": "action", "action": "fold"}
    return {"type": "action", "action": "call"}


def legalise(reply, m):
    """Last guard: the reply must be a legal action for this request."""
    legal = m.get("legal_actions", [])
    a = reply.get("action")
    if a not in legal:
        return safe_action(m)
    if a == "raise":
        lo, hi = int(m["min_raise"]), int(m["max_raise"])
        amt = int(reply.get("amount", lo))
        reply["amount"] = max(lo, min(hi, amt))
    return reply


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
        t = m.get("type")
        reply = None
        try:
            if t == "init":
                bot.on_init(m)
            elif t == "new_hand":
                bot.on_new_hand(m)
            elif t == "discard_result":
                bot.on_discard_result(m)
            elif t == "action_request":
                try:
                    reply = legalise(bot.act(m), m)
                except Exception as e:           # never crash
                    print("act error: %r" % (e,), file=sys.stderr)
                    reply = safe_action(m)
            elif t == "discard_request":
                try:
                    reply = bot.discard(m)
                except Exception as e:
                    print("discard error: %r" % (e,), file=sys.stderr)
                    cards = m.get("hole_cards", [])
                    worst = min(cards, key=lambda c: RANKS.index(c[0]))
                    reply = {"type": "discard", "card": worst}
            elif t == "match_end":
                break
        except Exception as e:
            print("handler error: %r" % (e,), file=sys.stderr)
        if reply is not None:
            out.write(json.dumps(reply) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
