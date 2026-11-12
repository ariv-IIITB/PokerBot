"""discardread v4: Bayesian read of the opponent's exposed discard (weight each candidate kept pair by how likely a sensible
keep it is given the flop), range-hit estimate drives bluffing; own discard breaks ties toward revealing little."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401


class Bot(BaseBot):
    def act(self, req):
        self._P = BASE
        if req["street"] != "preflop" and self.opp_discard is not None and self.board:
            self.eq(req)
            h = self._hit
            if h < 0.0:   # bluff boost disabled (ablation)                       # their range mostly missed this board: bluff more
                k = min(1.0, (0.45 - h) / 0.25)
                self._P = dict(BASE, semi=BASE["semi"] + 0.35 * k, river_bluff=BASE["river_bluff"] + 0.26 * k,
                               cbet=min(1.0, BASE["cbet"] + 0.35 * k))
        return super().act(req)

    def params(self):
        return self._P


if __name__ == "__main__":
    run(Bot)
