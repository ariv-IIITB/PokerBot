"""polar: bets 2x pot with its top 15% and with a matching share of bluffs from its bottom 15%; checks or calls the rest."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401


class Bot(BaseBot):
    def first_look(self, req, P):
        if req["street"] == "preflop" or req["to_call"] > 0:
            return None
        e = self.eq(req)
        if e >= 0.80:
            return self.size(req, 2.0)
        draw = req["street"] != "river" and has_draw(self.hole, self.board)
        if (e <= 0.25 and req["street"] == "river" or e <= 0.22 or draw) and self.rng.random() < 0.55 * min(1.5, self.opp.fold_rate / 0.35):
            return self.size(req, 2.0)                                # the bluffs that balance the value bets
        return "check"


if __name__ == "__main__":
    run(Bot)
