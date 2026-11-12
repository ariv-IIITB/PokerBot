"""potctl v4: pot control. Small bets with medium hands, pot-size bets with strong ones,
folds medium hands to bets over 3/4 pot. (v4 experiments did not beat the original; logic unchanged.)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401

P = dict(BASE, value=(0.50, 0.52, 0.55), cbet=0.55)


class Bot(BaseBot):
    P = P

    def bet_size(self, req, e, P, wet):
        if e >= 0.72:
            return 1.0
        return 0.33

    def first_look(self, req, P):
        if req["street"] == "preflop" or req["to_call"] == 0:
            return None
        e = self.eq(req)
        if 0.45 < e < 0.74 and self.bet_frac(req) > 0.75:
            return "fold"
        return None


if __name__ == "__main__":
    run(Bot)
