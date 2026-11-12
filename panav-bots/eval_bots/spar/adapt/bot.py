"""adapt: an exploiter. Opponent folds over 50% to our bets: bluff twice as often. Calls over 60%: no bluffs, thinner value bets. Re-checked every 20 hands."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401



class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self.mode = BASE

    def on_new_hand(self, msg):
        super().on_new_hand(msg)
        if self.hands % 20 == 1 and self.opp.faced >= 10:
            P = dict(BASE)
            if self.opp.fold_rate > 0.50:
                P.update(cbet=1.0, semi=BASE["semi"] * 2, river_bluff=BASE["river_bluff"] * 2)
            elif self.opp.call_rate > 0.60:
                P.update(semi=0.0, river_bluff=0.0, cbet=0.2, value=tuple(v - 0.07 for v in BASE["value"]))
            self.mode = P

    def params(self):
        return self.mode


if __name__ == "__main__":
    run(Bot)
