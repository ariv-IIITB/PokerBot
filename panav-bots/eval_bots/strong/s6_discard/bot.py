"""s6_discard: equity-vs-range bot whose identity is the discard.
 - our discard: simulated equity of each keep against an opponent who keeps the best 2 of 3 (draws counted),
   near-ties broken toward the discard that looks natural (hides our hand);
 - their exposed discard: a range weight P(they threw d | their 3 cards, flop), a mixture of three habit models
   (best-keep by flop strength, throw-lowest, throw-odd-suit) whose weights are learned in-leg from showdowns;
 - betting: common.BaseBot (percentile preflop, range-weighted Monte Carlo equity, pot odds, bets)."""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (BaseBot, run, score, has_draw, board_wet, card_to_int, log)  # noqa: E402


def keep_val(keep, flop):
    v = score(keep + flop)
    if has_draw(keep, flop):
        v += 1 << 19
    return v


def rank_of_keeps(cards, flop):
    """For the 3 cards: for each x, the rank r (0 best .. 2) of the keep that throws x (ties share the better rank)."""
    keeps = [[cards[j] for j in range(3) if j != i] for i in range(3)]
    vals = [keep_val(k, flop) for k in keeps]
    return [sum(1 for w in vals if w > v) for v in vals]


def hab_scores(cards):
    """Unnormalised likelihood of 'threw card i' under the lowest-card and odd-suit habits."""
    rk = [c >> 2 for c in cards]
    m = min(rk)
    low = [1.0 if r == m else 0.05 for r in rk]
    st = [c & 3 for c in cards]
    odd = [0.05] * 3
    for i in range(3):
        o = [st[j] for j in range(3) if j != i]
        if o[0] == o[1] and st[i] != o[0]:
            odd[i] = 1.0
    if max(odd) < 1.0:
        odd = [1.0] * 3
    return low, odd


class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self.rcnt = [0.75 * 6, 0.2 * 6, 0.05 * 6]      # rank-of-keep counts (prior)
        self.ll = [math.log(0.6), math.log(0.2), math.log(0.2)]
        self.dtime = 0.0

    # ---- opponent discard model
    def _probs(self):
        t = sum(self.rcnt)
        return [c / t for c in self.rcnt]

    def _post(self):
        m = max(self.ll)
        w = [math.exp(x - m) for x in self.ll]
        s = sum(w)
        return [x / s for x in w]

    def p_throw(self, cards, i, flop, rk=None, post=None, pr=None):
        """P(player throws cards[i] | the 3 cards), mixture over models."""
        post = post or self._post()
        pr = pr or self._probs()
        rk = rk or rank_of_keeps(cards, flop)
        low, odd = hab_scores(cards)
        p0 = [pr[r] for r in rk]
        res = 0.0
        for w, sc in zip(post, (p0, low, odd)):
            res += w * sc[i] / sum(sc)
        return res

    def on_hand_result(self, msg):
        try:
            if msg.get("result") == "showdown" and msg.get("opp_hole_cards") and msg.get("opp_discard") \
                    and len(msg.get("board", [])) >= 3:
                kept = [card_to_int(c) for c in msg["opp_hole_cards"]]
                d = card_to_int(msg["opp_discard"])
                flop = [card_to_int(c) for c in msg["board"][:3]]
                cards = kept + [d]
                i = 2
                rk = rank_of_keeps(cards, flop)
                low, odd = hab_scores(cards)
                p0 = [self._probs()[r] for r in rk]
                for m, sc in enumerate((p0, low, odd)):
                    self.ll[m] += math.log(max(1e-6, sc[i] / sum(sc)))
                self.ll = [x - max(self.ll) for x in self.ll]
                self.rcnt[rk[i]] += 1.0
        except Exception as exc:
            log("learn discard error", repr(exc))
        super().on_hand_result(msg)

    # ---- range equity with the discard weights
    def range_eq(self, p, n=150, tmax=0.007):
        hole, board, od = self.hole, self.board, self.opp_discard
        rng = self.rng
        known = set(hole) | set(board)
        if od is not None:
            known.add(od)
        rest = [c for c in range(52) if c not in known]
        need = 5 - len(board)
        flop = board[:3]
        use_d = od is not None and len(flop) == 3
        post, pr = self._post(), self._probs()
        recs, keys = [], []
        t_end = time.perf_counter() + tmax
        for i in range(n):
            if i & 15 == 15 and i >= 60 and time.perf_counter() > t_end:
                break
            s = rng.sample(rest, 2 + need)
            a, b = s[0], s[1]
            cur = score([a, b] + board)
            if need and p > 0.05 and has_draw([a, b], board):
                cur += 1 << 19
            wk = 1.0
            if use_d:
                wk = 3.0 * self.p_throw([a, b, od], 2, flop, post=post, pr=pr)
            recs.append((a, b, s[2:], wk))
            keys.append(cur)
        m = len(recs)
        u = [0.0] * m
        if p > 0.05:
            order = sorted(range(m), key=keys.__getitem__)
            for rank, idx in enumerate(order):
                u[idx] = (rank + 0.5) / m
        won = tot = 0.0
        for idx, (a, b, run_, wk) in enumerate(recs):
            w = wk * (u[idx] ** p if p > 0.05 else 1.0)
            full = board + run_
            mine = score(hole + full)
            th = score([a, b] + full)
            won += w * (1.0 if mine > th else 0.5 if mine == th else 0.0)
            tot += w
        return won / tot if tot > 0 else 0.5

    def eq(self, req):
        if self._eq is None:
            self._eq = self.range_eq(self.pressure(req))
        return self._eq

    # ---- our discard
    def discard(self, req):
        t0 = time.perf_counter()
        hole = [card_to_int(c) for c in req["hole_cards"]]
        flop = [card_to_int(c) for c in req["board"]]
        known = set(hole) | set(flop)
        rest = [c for c in range(52) if c not in known]
        keeps = [[hole[j] for j in range(3) if j != i] for i in range(3)]
        wins = [0.0] * 3
        n = 0
        rng = self.rng
        t_end = t0 + 0.012
        for i in range(300):
            if i & 15 == 15 and i >= 80 and time.perf_counter() > t_end:
                break
            s = rng.sample(rest, 5)
            o3 = s[:3]
            ok = [[o3[j] for j in range(3) if j != x] for x in range(3)]
            ov = [keep_val(k, flop) for k in ok]
            mv = max(ov)
            best = [k for k, v in zip(ok, ov) if v == mv]
            opp = best[rng.randrange(len(best))]
            full = flop + s[3:5]
            osc = score(opp + full)
            for j in range(3):
                m = score(keeps[j] + full)
                wins[j] += 1.0 if m > osc else 0.5 if m == osc else 0.0
            n += 1
        eqs = [w / max(1, n) for w in wins]
        top = max(eqs)
        low, odd = hab_scores(hole)
        cand = [i for i in range(3) if eqs[i] >= top - 0.006]
        # natural-looking discard: lowest card, odd suit; avoid throwing a card that pairs the board or is a flop suit
        def nat(i):
            c = hole[i]
            s = low[i] + odd[i]
            if any((f >> 2) == (c >> 2) for f in flop):
                s -= 0.5
            if sum(1 for f in flop if f & 3 == c & 3) >= 2:
                s -= 0.5
            return s
        i = max(cand, key=lambda i: (nat(i), eqs[i]))
        self.dtime += time.perf_counter() - t0
        return hole[i]


if __name__ == "__main__":
    run(Bot)
