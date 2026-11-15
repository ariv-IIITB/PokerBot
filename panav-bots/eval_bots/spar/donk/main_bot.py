"""donk: leads into the preflop raiser on every street with any pair or draw."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401


class Bot(BaseBot):
    def pair_or_draw(self):
        ranks = {c >> 2 for c in self.board}
        hr = [c >> 2 for c in self.hole]
        return any(r in ranks for r in hr) or len(set(hr)) < len(hr) or has_draw(self.hole, self.board)

    def first_look(self, req, P):
        if req["street"] == "preflop" or req["to_call"] > 0:
            return None
        if self.preflop_raiser(req) == "opp" and self.pair_or_draw():
            return self.size(req, 0.5)                                # the donk lead
        return None


if __name__ == "__main__":
    run(Bot)
