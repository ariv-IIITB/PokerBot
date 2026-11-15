"""betfold (v6-like): bets or raises about 60% postflop, almost never calls, folds about 70% when bet into. Hand strength picks which hands."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401

P = dict(BASE, open=0.40, defend=0.80, three=0.90)


class Bot(BaseBot):
    P = P

    def first_look(self, req, P):
        st, tc = req["street"], req["to_call"]
        if st == "preflop":
            return None
        e = self.eq(req)
        r = self.rng.random()
        opp = self.opp
        wet = board_wet(self.board)
        draw = st != "river" and has_draw(self.hole, self.board)
        fr = min(1.5, opp.fold_rate / 0.35)
        legal_raise = "raise" in req["legal_actions"] and self.raises_this_street(req) < 2
        if tc == 0:
            if e >= 0.50:
                f = self.rng.uniform(0.55, 0.85) + (0.15 if e >= 0.85 else 0.0)
                if opp.call_rate > 0.55:
                    f += 0.15                              # value-bet bigger against callers
                if st == "river" and e < 0.62 and r < 0.30:
                    return "check"                         # thin river hands keep showdown value
                return self.size(req, min(1.1, f))
            # bluffs: draws, then hands that cannot win at showdown (river air), then a few weak-showdown hands
            p = 0.0
            if draw:
                p = 0.75
            elif st == "river":
                p = 0.55 if e < 0.25 else 0.15
            else:
                p = 0.35 if e < 0.30 else 0.20
            if wet and not draw:
                p *= 0.8
            p *= min(1.3, 0.6 + 0.6 * fr)
            if r < p:
                return self.size(req, 0.50 + 0.15 * (1 if fr < 1.0 else 0))
            return "check"
        # facing a bet
        if e >= 0.80 and legal_raise:
            return self.size(req, 0.75)
        if e >= 0.66:
            return "call"                                  # never fold strong hands
        if e >= 0.58 and r < 0.25:
            return "call"
        if legal_raise and draw and st == "flop" and self.raises_this_street(req) == 0 and r < 0.18 * fr:
            return self.size(req, 0.7)                     # semi-bluff raise
        if legal_raise and st == "river" and e < 0.12 and r < 0.05 * fr:
            return self.size(req, 0.7)
        return "fold"


if __name__ == "__main__":
    run(Bot)
