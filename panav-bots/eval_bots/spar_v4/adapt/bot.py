"""adapt (v4): an exploiter that measures the opponent continuously (Bayesian rates, per street) and moves every
parameter smoothly: bluff more against over-folders, steal preflop, never bluff and value-bet thinner against
calling stations, call down lighter against maniacs. No fixed clock."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401


def clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self.mode = BASE
        self.cur_street = "flop"

    def rate(self, streets, idx, prior, k=6.0):
        n = f = 0
        for s in streets:
            t = self.opp.sf.get(s)
            if t:
                n += t[0]
                f += t[idx]
        return (f + prior * k) / (n + k), n

    def on_new_hand(self, msg):
        super().on_new_hand(msg)
        self.mode = self.build()

    def build(self):
        o = self.opp
        fold, n = self.rate(("flop", "turn", "river"), 1, 0.35)
        call, _ = self.rate(("flop", "turn", "river"), 2, 0.50)
        pfold, pn = self.rate(("preflop",), 1, 0.30, 5.0)
        # confidence grows with sample size
        conf = clip(n / 12.0, 0.0, 1.0)
        x = clip((fold - 0.47) / 0.20, 0.0, 1.5) * conf          # over-folder score
        y = clip((call - 0.58) / 0.15, 0.0, 1.0) * conf          # station score
        P = dict(BASE)
        P["cbet"] = clip(0.65 + 0.35 * x - 0.45 * y, 0.15, 1.0)
        P["semi"] = BASE["semi"] * (1 + 1.2 * x) * (1 - y)
        P["river_bluff"] = BASE["river_bluff"] * (1 + 1.5 * x) * (1 - y)
        P["value"] = tuple(v - 0.07 * y for v in BASE["value"])
        P["size_value"] = 0.0
        if o.bet_rate > 0.5:
            P["margin"] = 0.0                                     # call down lighter vs maniacs
        # preflop steals against over-folders
        px = clip((pfold - 0.68) / 0.17, 0.0, 1.0) * clip(pn / 10.0, 0, 1)
        P["open"] = BASE["open"] - 0.08 * px
        P["limp"] = BASE["limp"] - 0.03 * px
        P["bb_raise"] = BASE["bb_raise"] - 0.06 * px
        return P

    def params(self):
        return self.mode


if __name__ == "__main__":
    run(Bot)
