"""s4_balanced: game-theory rules of thumb on top of the equity / range machinery of common.py.

  - betting range: value bets when equity vs their range is high; bluffs are drawn from the weakest percentile of
    our own plausible range (draws first) so that bluffs / (bluffs + value) = bet / (pot + 2 * bet) for the size used;
  - facing a bet: defend at least pot / (pot + bet) of our range (minimum defence), and call whenever equity beats
    the pot-odds indifference point against their (bet-narrowed) range;
  - sizing: big (~0.75 pot) for strong value and for bluffs, small (~0.4) for thin value, so the big bets are
    balanced; small bets are never bluffs;
  - hand strength is both the equity (vs their range) and the percentile among random hands on this board.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (BASE, BaseBot, run, board_wet, has_draw, score, best_score, STREET_R)  # noqa: E402


BLUFF = float(os.environ.get('S4_BLUFF', '0'))
MDF = int(os.environ.get('S4_MDF', '0'))


class Bot(BaseBot):
    P = dict(BASE)

    def my_pct(self):
        """Percentile of our current hand among random hands on this board (draws count as a bump)."""
        if getattr(self, "_u", None) is not None:
            return self._u
        known = set(self.hole) | set(self.board)
        if self.my_discard is not None:
            known.add(self.my_discard)
        rest = [c for c in range(52) if c not in known]
        k = 3 if len(self.hole) == 3 else 2
        river = len(self.board) >= 5
        mine = best_score(self.hole, self.board)
        if not river and has_draw(self.hole[:2] if k == 3 else self.hole, self.board):
            mine += 1 << 19
        lo = 0.0
        n = 70
        for _ in range(n):
            s = self.rng.sample(rest, k)
            v = best_score(s, self.board)
            if not river and has_draw(s[:2], self.board):
                v += 1 << 19
            lo += 1.0 if mine > v else 0.5 if mine == v else 0.0
        self._u = lo / n
        return self._u

    def on_new_hand(self, msg):
        BaseBot.on_new_hand(self, msg)
        self._u = None

    def on_discard_result(self, msg):
        BaseBot.on_discard_result(self, msg)
        self._u = None

    def act(self, req):
        self._u = None
        P = self.P
        if req["street"] == "preflop":
            return self.preflop(req, P)
        if os.environ.get('S4_OLD'):
            return self.balanced(req)
        return self.layered(req)

    def layered(self, req):
        r = BaseBot.postflop(self, req, self.P)
        st, tc = req['street'], req['to_call']
        if tc > 0:
            if r == 'fold' and MDF and 'call' in req['legal_actions']:
                e = self.eq(req)
                f = tc / float(max(1, req['pot'] - tc))
                need = self.odds(req) / min(1.0, STREET_R[st]) + 0.015
                defend = min(0.5, 0.65 / (1.0 + f))
                if e >= need - 0.05 and self.my_pct() >= 1.0 - defend:
                    return 'call'
            return r
        if r == 'check' and BLUFF and 'raise' in req['legal_actions'] and st != 'flop':
            u = self.my_pct()
            e = self.eq(req)
            draw = st != 'river' and has_draw(self.hole, self.board)
            s_big = 0.70
            b = 0.25 * s_big / (1.0 + s_big)
            w = b / 0.35 if (u < 0.35 or draw) else 0.0
            w *= min(1.6, self.opp.fold_rate / 0.35) * (0.3 if self.opp.call_rate > 0.6 else 1.0) * BLUFF
            if self.rng.random() < w:
                return self.size(req, s_big)
        return r

    def balanced(self, req):
        st, tc = req["street"], req["to_call"]
        e = self.eq(req)
        u = self.my_pct()
        wet = board_wet(self.board)
        draw = st != "river" and has_draw(self.hole, self.board)
        ip = self.in_position()
        opp = self.opp
        rng = self.rng
        pot = req["pot"]
        legal_raise = "raise" in req["legal_actions"]
        if tc > 0:
            f = tc / float(max(1, pot - tc))                  # bet as a fraction of the pot before it
            mdf = 1.0 / (1.0 + f)                              # minimum defence frequency
            R = min(1.0, STREET_R[st] + (0.03 if ip else 0.0))
            need = self.odds(req) / R + 0.015                  # indifference point
            if opp.bet_rate > 0.55:
                need -= 0.03
            nr = self.raises_this_street(req)
            big = e >= 0.84 + (0.03 if st == "river" else 0.0)
            if legal_raise and nr < 2 and big:
                return self.size(req, 0.75)
            if legal_raise and nr == 0 and st != "river" and draw and e >= need - 0.14:
                # bluff-raise: with value-raises ~ top 12%, bluffs ~ a third of that with the best draws
                if rng.random() < 0.28 * min(1.5, opp.fold_rate / 0.35):
                    return self.size(req, 0.75)
            if e >= need - 0.005:
                return "call"
            # minimum defence: keep calling the top part of the range even when the equity estimate is pessimistic
            # (their range is not as narrow as the weights say); capped so we are not a station
            defend = min(0.50, 0.65 * mdf)
            if MDF and e >= need - 0.04 and u >= 1.0 - defend:
                return "call"
            if abs(e - need) < 0.02:
                return "call" if rng.random() < 0.5 else "fold"
            return "fold"
        # ---- nobody has bet: value, thin value, bluffs
        pre_agg = self.preflop_raiser(req) == "me"
        thr_big = (0.68, 0.70, 0.72)[("flop", "turn", "river").index(st)]
        thr_thin = (0.56, 0.58, 0.62)[("flop", "turn", "river").index(st)] + (0.0 if ip else 0.03)
        if opp.call_rate > 0.65:
            thr_thin -= 0.04
            thr_big -= 0.03
        if not legal_raise:
            return "check"
        s_big = 0.80 if wet else 0.70
        if e >= thr_big:
            if not ip and st == "flop" and e < 0.88 and rng.random() < 0.25:
                return "check"                                  # a few slow plays out of position keep the check range strong
            return self.size(req, s_big)
        if e >= thr_thin:
            return self.size(req, 0.50)
        # bluff mass: share of the whole range that bets big for value times s / (1 + s)
        pv = 0.30 if st != "river" else 0.28
        b = pv * s_big / (1.0 + s_big)
        pool = 0.40
        w = b / pool
        if draw:
            w = min(0.7, w * 2.2)
        elif st == "flop" and pre_agg and not wet and u > 0.30:
            return self.size(req, 0.33) if rng.random() < 0.55 else "check"   # range bet, small, on dry boards
        elif u > pool:
            w = 0.0
        if opp.call_rate > 0.6:
            w *= 0.3
        w *= min(1.6, opp.fold_rate / 0.35)
        if st == "river" and u > 0.2:
            w *= 0.5
        if not ip:
            w *= 0.8
        w *= BLUFF
        if rng.random() < w:
            return self.size(req, s_big)
        return "check"


if __name__ == "__main__":
    run(Bot)
