"""potctl: pot control. Small bets with medium hands, pot-size bets with strong ones, folds medium hands to bets over 3/4 pot."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401

P = dict(BASE, value=(0.50, 0.52, 0.55), cbet=0.55)


class Bot(BaseBot):
    P = P

    def bet_size(self, req, e, P, wet):
        return 1.0 if e >= 0.72 else 0.33

    def first_look(self, req, P):
        if req["street"] == "preflop" or req["to_call"] == 0:
            return None
        e = self.eq(req)
        if 0.45 < e < 0.74 and self.bet_frac(req) > 0.75:
            return "fold"                                             # medium hands give up to big bets
        return None


if __name__ == "__main__":
    run(Bot)
