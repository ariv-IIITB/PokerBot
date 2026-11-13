"""h4_trapper: Discard Hold'em bot (heads-up). Single file, stdlib only.

Style: tight and patient. Narrow strong opening range, slowplays very strong hands on the flop
and turn (check to induce, check-raise), raises c-bets with strong hands and big draws, calls
down medium hands only when pot odds and the opponent's bluff frequency justify it, rarely
bluffs, bets big on the river with value. Equity comes from Monte Carlo against a range that is
narrowed by the opponent's actions (weights on sampled opponent hands); discard by equity.
"""
import json
import random
import sys
import time

RANKS = "23456789TJQKA"
SUITS = "shdc"
CARD_ID = {r + s: i * 4 + j for i, r in enumerate(RANKS) for j, s in enumerate(SUITS)}
ID_CARD = {v: k for k, v in CARD_ID.items()}
ALL_CARDS = list(range(52))


# --------------------------------------------------------------------------- evaluator

def _straight_high(mask: int) -> int:
    """Highest rank index of a straight in the rank bitmask (wheel = 3), or -1."""
    m = (mask << 1) | (1 if mask & (1 << 12) else 0)
    for h in range(12, 2, -1):
        if (m >> (h - 3)) & 31 == 31:
            return h
    return -1


def _pack(ks) -> int:
    v = 0
    for k in ks:
        v = v * 13 + k
    return v


def evaluate(cards) -> int:
    """Strength of the best 5-card hand among 5..7 cards (ints rank*4+suit). Higher is better."""
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
        h = _straight_high(fm)
        if h >= 0:
            return (8 << 20) | h
    quads = -1
    trips = []
    pairs = []
    singles = []
    for r in range(12, -1, -1):
        n = cnt[r]
        if n == 4:
            quads = r
        elif n == 3:
            trips.append(r)
        elif n == 2:
            pairs.append(r)
        elif n == 1:
            singles.append(r)
    if quads >= 0:
        rest = [r for r in range(12, -1, -1) if cnt[r] and r != quads]
        return (7 << 20) | _pack([quads, rest[0]])
    if trips and (len(trips) > 1 or pairs):
        second = max(trips[1:] + pairs)
        return (6 << 20) | _pack([trips[0], second])
    if fs >= 0:
        top = [r for r in range(12, -1, -1) if any((c & 3) == fs and (c >> 2) == r for c in cards)]
        return (5 << 20) | _pack(top[:5])
    h = _straight_high(mask)
    if h >= 0:
        return (4 << 20) | h
    if trips:
        ks = [r for r in range(12, -1, -1) if cnt[r] and r != trips[0]][:2]
        return (3 << 20) | _pack([trips[0]] + ks)
    if len(pairs) >= 2:
        rest = [r for r in range(12, -1, -1) if cnt[r] and r != pairs[0] and r != pairs[1]]
        return (2 << 20) | _pack([pairs[0], pairs[1], rest[0]])
    if pairs:
        ks = [r for r in range(12, -1, -1) if cnt[r] and r != pairs[0]][:3]
        return (1 << 20) | _pack([pairs[0]] + ks)
    return _pack(singles[:5])


def pre_score(three) -> int:
    """Cheap preflop strength proxy of 3 cards: the best 2-card keep."""
    best = -1
    for i in range(3):
        a, b = [three[j] for j in range(3) if j != i]
        ra, rb = a >> 2, b >> 2
        hi, lo = max(ra, rb), min(ra, rb)
        s = hi * 2 + lo
        if hi == lo:
            s += 14
        if (a & 3) == (b & 3):
            s += 4
        gap = hi - lo
        if gap == 1:
            s += 3
        elif gap == 2:
            s += 2
        best = max(best, s)
    # third card: suit/connection synergy bonus
    ranks = sorted(c >> 2 for c in three)
    if three[0] & 3 == three[1] & 3 == three[2] & 3:
        best += 2
    if ranks[2] - ranks[0] <= 4:
        best += 1
    return best


# --------------------------------------------------------------------------- samples

class Samples:
    """Monte Carlo samples for one decision stage. Weights are recomputed per request."""

    def __init__(self, stage, metrics, results):
        self.stage = stage
        n = len(metrics)
        order = sorted(range(n), key=lambda i: metrics[i])
        self.p = [0.0] * n
        for rank, i in enumerate(order):
            self.p[i] = (rank + 0.5) / n
        self.results = results           # results[i] = list of outcomes (one per option) in 0/.5/1
        self.n = n


def _outcome(a: int, b: int) -> float:
    return 1.0 if a > b else (0.5 if a == b else 0.0)


def make_samples(rng, stage, mine, board, dead_extra, n):
    """stage 'A' preflop (3 cards, no board), 'B' flop before discard (3 cards, 3 board),
    'C' turn / 'D' river (2 kept cards, known board)."""
    known = set(mine) | set(board) | set(dead_extra)
    deck = [c for c in ALL_CARDS if c not in known]
    metrics = []
    results = []
    sample = rng.sample
    if stage == "A":
        for _ in range(n):
            draw = sample(deck, 8)
            opp = draw[:3]
            bd = draw[3:]
            mine_best = max(evaluate([mine[a], mine[b]] + bd) for a, b in ((0, 1), (0, 2), (1, 2)))
            opp_best = max(evaluate([opp[a], opp[b]] + bd) for a, b in ((0, 1), (0, 2), (1, 2)))
            metrics.append(pre_score(opp))
            results.append([_outcome(mine_best, opp_best)])
    elif stage == "B":
        keeps = ((0, 1), (0, 2), (1, 2))
        for _ in range(n):
            draw = sample(deck, 5)
            opp = draw[:3]
            run = draw[3:]
            full = board + run
            best = None
            bs = -1
            for a, b in ((0, 1), (0, 2), (1, 2)):
                s5 = evaluate([opp[a], opp[b]] + board)
                tie = (opp[a] >> 2) + (opp[b] >> 2)
                key = s5 * 32 + tie
                if key > bs:
                    bs = key
                    best = (a, b)
            o7 = evaluate([opp[best[0]], opp[best[1]]] + full)
            metrics.append(bs)
            results.append([_outcome(evaluate([mine[a], mine[b]] + full), o7) for a, b in keeps])
    else:
        need_run = 5 - len(board)
        for _ in range(n):
            draw = sample(deck, 2 + need_run)
            opp = draw[:2]
            full = board + draw[2:]
            metrics.append(evaluate(opp + board))
            results.append([_outcome(evaluate(list(mine) + full), evaluate(opp + full))])
    return Samples(stage, metrics, results)


# --------------------------------------------------------------------------- bot

class Bot:
    def __init__(self):
        self.rng = random.Random()
        self.total_hands = 400
        self.time_bank = 30000
        # opponent stats (accumulated at hand_result)
        self.pf_raise = 0
        self.pf_n = 0
        self.po_aggr = 0
        self.po_n = 0
        self.fold_faced = 0
        self.fold_n = 0
        self.new_hand_state(None)
        self.hands_seen = 0

    # ---- state
    def new_hand_state(self, msg):
        self.seat = msg.get("seat") if msg else None
        self.hole = [CARD_ID[c] for c in msg["hole_cards"]] if msg else []
        self.kept = None
        self.my_discard = None
        self.opp_discard = None
        self.hist = []
        self.cache = {}
        self.last_board = []
        if msg:
            self.hands_seen += 1

    # ---- opponent model
    def af(self):
        return (self.po_aggr + 3.0) / (self.po_n + 9.0)

    def pfr(self):
        return (self.pf_raise + 3.0) / (self.pf_n + 9.0)

    def fold_freq(self):
        return (self.fold_n + 3.0) / (self.fold_faced + 6.0)

    def update_stats(self, hist):
        me_last_raise = {}
        for e in hist:
            st = e.get("street")
            a = e.get("action")
            who = e.get("actor")
            if who == "opp":
                if st == "preflop":
                    self.pf_n += 1
                    if a == "raise":
                        self.pf_raise += 1
                else:
                    if a in ("raise", "check", "call"):
                        self.po_n += 1
                        if a == "raise":
                            self.po_aggr += 1
                    if me_last_raise.get(st) and a in ("fold", "call", "raise"):
                        self.fold_faced += 1
                        if a == "fold":
                            self.fold_n += 1
                me_last_raise[st] = False
            else:
                me_last_raise[st] = (a == "raise")

    # ---- weights from the opponent's actions this hand
    def parse_opp_actions(self, hist, seat):
        """Return [(street, action, size_ratio)] for the opponent's actions this hand."""
        out = []
        base = 0
        bets = {"me": 0, "opp": 0}
        if seat == "button":
            bets["me"], bets["opp"] = 1, 2
        else:
            bets["me"], bets["opp"] = 2, 1
        base = 0
        cur = "preflop"
        for e in hist:
            st = e.get("street", cur)
            if st != cur:
                base += bets["me"] + bets["opp"]
                bets = {"me": 0, "opp": 0}
                cur = st
            a = e.get("action")
            who = e.get("actor")
            if who not in bets:
                continue
            amt = e.get("amount", 0) or 0
            if who == "opp":
                pot_before = base + bets["me"] + bets["opp"]
                if a == "raise":
                    ratio = (amt - bets["opp"]) / float(max(pot_before, 4))
                    out.append((st, "raise", ratio))
                elif a in ("call", "check", "fold"):
                    out.append((st, a, 0.0))
            if a in ("call", "raise"):
                bets[who] = amt
        return out

    def weights(self, S, hist, seat):
        n = S.n
        w = [1.0] * n
        acts = self.parse_opp_actions(hist, seat)
        af_scale = min(1.3, max(0.55, 1.25 - 1.2 * (self.af() - 0.33)))
        pf_scale = min(1.3, max(0.6, 1.2 - 1.0 * (self.pfr() - 0.35)))
        eps_post = 0.05 + max(0.0, min(0.2, (self.af() - 0.33) * 0.6))
        stage_is_pre = S.stage == "A"
        raises_pre = 0
        for st, a, ratio in acts:
            pre = st == "preflop"
            if pre and a == "raise":
                raises_pre += 1
            for i in range(n):
                p = S.p[i]
                if a == "raise":
                    if pre:
                        k = (1.7 + 1.3 * (raises_pre - 1)) * pf_scale
                        if not stage_is_pre:
                            k *= 0.45
                        f = 0.04 + 0.96 * (p ** k)
                    else:
                        k = 1.5 * af_scale * (0.7 + 0.6 * min(ratio, 2.0))
                        f = eps_post + (1 - eps_post) * (p ** k)
                elif a == "call":
                    if pre:
                        f = 1.0 if not stage_is_pre else min(1.0, 0.25 + 1.5 * p)
                    else:
                        f = min(1.0, 0.12 + 1.6 * p)
                elif a == "check":
                    f = 1.0 if pre else 1.0 - 0.45 * (p ** 3)
                else:
                    f = 1.0
                w[i] *= f
        tot = sum(w)
        if tot < 1e-9:
            return [1.0] * n
        # keep an effective-sample floor: blend a little uniform mass back in
        neff = tot * tot / max(sum(x * x for x in w), 1e-12)
        if neff < 12:
            m = tot / n
            w = [0.7 * x + 0.3 * m for x in w]
        return w

    @staticmethod
    def equity(S, w, opt=0):
        tot = 0.0
        acc = 0.0
        for i in range(S.n):
            tot += w[i]
            acc += w[i] * S.results[i][opt]
        return acc / tot if tot > 0 else 0.5

    # ---- samples with cache
    def get_samples(self, stage, mine, board, n, time_left):
        if time_left < 4000:
            n = max(30, n // 4)
        elif time_left < 10000:
            n = max(50, n // 2)
        key = (stage, tuple(mine), tuple(board), self.opp_discard)
        S = self.cache.get(key)
        if S is None:
            dead = [d for d in (self.my_discard, self.opp_discard) if d is not None]
            S = make_samples(self.rng, stage, mine, board, dead, n)
            self.cache[key] = S
        return S

    # ---- draws
    def draw_outs(self, kept, board):
        """Outs to a straight/flush for a hand not yet that strong (7-card or fewer)."""
        base = evaluate(list(kept) + list(board))
        if base >> 20 >= 4:
            return 0
        seen = set(kept) | set(board)
        outs = 0
        for c in ALL_CARDS:
            if c in seen:
                continue
            if evaluate(list(kept) + list(board) + [c]) >> 20 >= 4:
                outs += 1
        return outs

    # ---- helpers for actions
    def clamp_raise(self, req, amount):
        lo = req.get("min_raise", 0)
        hi = req.get("max_raise", 0)
        amount = int(amount)
        amount = max(lo, min(hi, amount))
        # shove when most of the stack is already going in
        if hi and amount >= 0.55 * hi:
            amount = hi
        return {"type": "action", "action": "raise", "amount": int(amount)}

    @staticmethod
    def passive(req):
        legal = req["legal_actions"]
        if "check" in legal:
            return {"type": "action", "action": "check"}
        if "call" in legal:
            return {"type": "action", "action": "call"}
        return {"type": "action", "action": "fold"}

    def bet_frac(self, req, frac):
        P = req["pot"]
        base = req.get("opp_bet", 0)
        return self.clamp_raise(req, base + max(2, int(frac * P)))

    # ---- decisions
    def act(self, req):
        legal = req["legal_actions"]
        street = req["street"]
        board = [CARD_ID[c] for c in req.get("board", [])]
        tl = req.get("time_left_ms", 30000)
        self.hist = req.get("history", [])
        self.last_board = board
        rng = self.rng
        P = req["pot"]
        c = req.get("to_call", 0)
        can_raise = "raise" in legal
        need = c / float(P + c) if c > 0 else 0.0

        if street == "preflop":
            S = self.get_samples("A", self.hole, [], 150, tl)
            w = self.weights(S, self.hist, self.seat)
            e = self.equity(S, w)
            return self.preflop(req, e, need, can_raise)

        if street == "flop":
            S = self.get_samples("B", self.hole, board, 130, tl)
            w = self.weights(S, self.hist, self.seat)
            opts = [self.equity(S, w, j) for j in range(3)]
            j = max(range(3), key=lambda k: opts[k])
            e = opts[j]
            keep = [self.hole[a] for a in ((0, 1), (0, 2), (1, 2))[j]]
        else:
            if self.kept is None or len(self.kept) != 2:
                return self.passive(req)
            keep = self.kept
            S = self.get_samples("C" if street == "turn" else "D", keep, board, 220, tl)
            w = self.weights(S, self.hist, self.seat)
            e = self.equity(S, w)
        return self.postflop(req, e, need, can_raise, street, keep, board)

    def preflop(self, req, e, need, can_raise):
        rng = self.rng
        c = req.get("to_call", 0)
        opp_bet = req.get("opp_bet", 0)
        my_bet = req.get("my_bet", 0)
        legal = req["legal_actions"]
        facing_raise = opp_bet > 2
        if not facing_raise:
            # button open (opp_bet == 2), or BB facing a limp (to_call == 0)
            if c > 0:
                if e >= 0.545 and can_raise:
                    return self.clamp_raise(req, rng.choice((5, 6, 6, 7)))
                if e >= 0.47 and rng.random() < 0.15 and can_raise:
                    return self.clamp_raise(req, 6)          # rare light open
                return {"type": "action", "action": "fold"}
            if e >= 0.60 and can_raise:
                return self.clamp_raise(req, rng.choice((6, 7, 8)))
            return {"type": "action", "action": "check"}
        # facing a raise
        if e >= 0.66 and can_raise:
            # strong: mostly re-raise, sometimes flat to trap
            if rng.random() < 0.30 and c < 40:
                return {"type": "action", "action": "call"}
            return self.clamp_raise(req, opp_bet * 3 + rng.choice((0, 2, 4)))
        if e >= need + 0.07:
            return {"type": "action", "action": "call"}
        if "call" in legal and c <= 2 and e >= need:
            return {"type": "action", "action": "call"}
        return {"type": "action", "action": "fold"}

    def postflop(self, req, e, need, can_raise, street, keep, board):
        rng = self.rng
        P = req["pot"]
        c = req.get("to_call", 0)
        legal = req["legal_actions"]
        river = street == "river"
        fold_f = self.fold_freq()
        af = self.af()
        station = fold_f < 0.30
        # how much the opponent's bluffing lowers our calling margin
        margin = max(0.0, min(0.09, 0.055 - 0.10 * (af - 0.33)))

        if c == 0:                                     # first to act, or checked to
            if not can_raise:
                return {"type": "action", "action": "check"}
            if e >= 0.86:
                if river:
                    return self.bet_frac(req, rng.choice((0.8, 1.0, 1.0, 1.25)))
                if rng.random() < 0.62:                # trap: induce
                    return {"type": "action", "action": "check"}
                return self.bet_frac(req, rng.choice((0.5, 0.65, 0.8)))
            if e >= 0.68:
                if river:
                    return self.bet_frac(req, rng.choice((0.5, 0.65, 0.75)))
                if rng.random() < 0.20:
                    return {"type": "action", "action": "check"}
                return self.bet_frac(req, rng.choice((0.6, 0.7, 0.8)))
            if station and e >= 0.58:
                return self.bet_frac(req, 0.4)         # thin value vs a station
            if river and e < 0.30 and not station and fold_f > 0.50 and rng.random() < 0.08:
                return self.bet_frac(req, 0.7)         # rare river bluff
            return {"type": "action", "action": "check"}

        # facing a bet
        outs = 0
        if not river:
            outs = self.draw_outs(keep, board)
        big_draw = outs >= 8
        if can_raise:
            if e >= 0.90 and rng.random() < 0.78:      # check-raise / raise for value
                return self.raise_over(req, 0.8 if not river else 0.7)
            if e >= 0.76 and not river and rng.random() < 0.45:
                return self.raise_over(req, 0.7)
            if e >= 0.85 and river and rng.random() < 0.35:
                return self.raise_over(req, 0.7)
            if big_draw and not river and rng.random() < 0.30 and c <= 0.8 * (P - c):
                return self.raise_over(req, 0.7)       # semi-bluff
        if e >= need + margin:
            return {"type": "action", "action": "call"}
        if big_draw and not river:
            # implied odds on a big draw: price it a little better than raw equity
            if e + 0.06 >= need:
                return {"type": "action", "action": "call"}
        return {"type": "action", "action": "fold"}

    def raise_over(self, req, mult):
        P = req["pot"]
        c = req.get("to_call", 0)
        opp_bet = req.get("opp_bet", 0)
        return self.clamp_raise(req, opp_bet + int(mult * (P + c)))

    def discard(self, req):
        cards = [CARD_ID[c] for c in req["hole_cards"]]
        board = [CARD_ID[c] for c in req["board"]]
        tl = req.get("time_left_ms", 30000)
        self.hole = cards
        S = self.get_samples("B", cards, board, 130, tl)
        w = self.weights(S, self.hist, self.seat)
        opts = [self.equity(S, w, j) for j in range(3)]
        j = max(range(3), key=lambda k: opts[k])
        keep = ((0, 1), (0, 2), (1, 2))[j]
        gone = [i for i in range(3) if i not in keep][0]
        return {"type": "discard", "card": ID_CARD[cards[gone]]}

    def fallback_discard(self, req):
        cards = req["hole_cards"]
        worst = min(cards, key=lambda c: RANKS.index(c[0]))
        return {"type": "discard", "card": worst}


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
        t = msg.get("type")
        reply = None
        try:
            if t == "init":
                bot.total_hands = msg.get("total_hands", 400)
                bot.time_bank = msg.get("time_bank_ms", 30000)
            elif t == "new_hand":
                bot.new_hand_state(msg)
            elif t == "action_request":
                try:
                    reply = bot.act(msg)
                except Exception as exc:                # never crash: legal fallback
                    print("act error: %r" % (exc,), file=sys.stderr)
                    reply = Bot.passive(msg)
            elif t == "discard_request":
                try:
                    reply = bot.discard(msg)
                except Exception as exc:
                    print("discard error: %r" % (exc,), file=sys.stderr)
                    reply = bot.fallback_discard(msg)
            elif t == "discard_result":
                bot.my_discard = CARD_ID.get(msg.get("my_discard"))
                bot.opp_discard = CARD_ID.get(msg.get("opp_discard"))
                bot.kept = [CARD_ID[c] for c in msg.get("hole_cards", [])]
            elif t == "hand_result":
                bot.update_stats(msg.get("history", []))
            elif t == "match_end":
                break
        except Exception as exc:
            print("loop error: %r" % (exc,), file=sys.stderr)
            if t == "action_request":
                reply = Bot.passive(msg)
            elif t == "discard_request":
                reply = bot.fallback_discard(msg)
        if reply is not None:
            out.write(json.dumps(reply) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
