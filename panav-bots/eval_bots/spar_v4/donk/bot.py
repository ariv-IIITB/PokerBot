"""donk v4: leads into the preflop raiser with pair/draw hands, sized by strength and board; folds/continues by equity."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401

PV4 = dict(BASE, defend=0.30, margin=0.02)


class Bot(BaseBot):
    P = PV4

    def pair_or_draw(self):
        ranks = {c >> 2 for c in self.board}
        hr = [c >> 2 for c in self.hole]
        return any(r in ranks for r in hr) or len(set(hr)) < len(hr) or has_draw(self.hole, self.board)

    def first_look(self, req, P):
        if req["street"] == "preflop" or req["to_call"] > 0:
            return None
        if self.preflop_raiser(req) != "opp" or "raise" not in req["legal_actions"]:
            return None
        if not self.pair_or_draw():
            return None
        st = req["street"]
        e = self.eq(req)
        wet = board_wet(self.board)
        draw = st != "river" and has_draw(self.hole, self.board)
        opp = self.opp
        station = opp.call_rate > 0.62
        fr = opp.fold_rate
        r = self.rng.random()
        if e >= 0.72:                                   # strong: bigger, bigger still vs a station
            f = 0.75 if wet else 0.6
            if station:
                f += 0.15
            return self.size(req, f)
        if e >= 0.52:                                   # medium value / protection
            return self.size(req, 0.55 if wet else 0.42)
        if draw and st != "river":                      # semi-bluff, more when they fold
            if station and e < 0.40:
                return None
            if r < min(1.0, 0.55 + 0.6 * fr):
                return self.size(req, 0.5)
            return None
        if st == "river":
            return None                                  # weak pair: check, then fold to a big bet
        if e >= 0.40 and r < 0.6 and not station:
            return self.size(req, 0.33)                 # small probe with a weak pair
        return None


if __name__ == "__main__":
    run(Bot)
