"""s10_regret: a portfolio of eight sound strategies (parameter sets over one shared equity engine) with an
EXP3/Hedge learner that picks one per hand and updates from the chips won. Strong prior on the default."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run  # noqa: E402


def mk(**kw):
    d = dict(BASE)
    d.update(kw)
    return d


POLICIES = [
    ("default", mk()),
    ("tight_value", mk(open=0.34, defend=0.42, three=0.92, three_bluff=0.04, value=(0.64, 0.66, 0.72),
                       semi=0.20, river_bluff=0.06, cbet=0.55)),
    ("aggr_bluff", mk(open=0.18, limp=0.10, defend=0.30, three=0.82, three_bluff=0.18, value=(0.57, 0.59, 0.64),
                      semi=0.55, river_bluff=0.24, cbet=0.85, raise_val=0.80)),
    ("pot_control", mk(three=0.93, three_bluff=0.05, raise_val=0.90, value=(0.62, 0.64, 0.68),
                       size_dry=0.40, size_wet=0.55, semi=0.25, river_bluff=0.08, cbet=0.55, margin=0.02)),
    ("polar", mk(value=(0.64, 0.66, 0.72), size_dry=0.70, size_wet=0.90, size_value=0.15, semi=0.50,
                 river_bluff=0.30, cbet=0.65, raise_val=0.82)),
    ("station_beater", mk(value=(0.54, 0.54, 0.58), size_dry=0.60, size_wet=0.80, size_value=0.10,
                          semi=0.10, river_bluff=0.0, cbet=0.45, three_bluff=0.03, margin=0.04)),
    ("position_aggr", mk(open=0.20, limp=0.12, defend=0.32, three=0.84, three_bluff=0.16, bb_raise=0.50,
                         value=(0.58, 0.60, 0.66), semi=0.45, cbet=0.80, river_bluff=0.18)),
    ("callwide", mk(defend=0.30, call3=0.54, margin=0.0, value=(0.62, 0.64, 0.70), semi=0.30,
                    river_bluff=0.10, raise_val=0.88)),
]
N = len(POLICIES)
PRIOR = [0.40] + [0.60 / (N - 1)] * (N - 1)


class Bot(BaseBot):
    ETA = 0.06          # learning rate on importance-weighted rewards in units of 100 chips
    GAMMA = 0.10        # uniform exploration mix

    def __init__(self):
        super().__init__()
        self.S = [0.0] * N
        self.cur = 0
        self.prob = 1.0
        self.mean = 0.0
        self.nrew = 0
        self.P = POLICIES[0][1]

    def probs(self):
        m = max(self.S)
        w = [PRIOR[i] * math.exp(self.ETA * (self.S[i] - m)) for i in range(N)]
        t = sum(w)
        return [(1 - self.GAMMA) * x / t + self.GAMMA / N for x in w]

    def on_new_hand(self, msg):
        super().on_new_hand(msg)
        pr = self.probs()
        r = self.rng.random()
        acc = 0.0
        self.cur = N - 1
        for i in range(N):
            acc += pr[i]
            if r < acc:
                self.cur = i
                break
        self.prob = pr[self.cur]
        self.P = POLICIES[self.cur][1]

    def on_hand_result(self, msg):
        super().on_hand_result(msg)
        try:
            x = float(msg.get("net", 0)) / 100.0
            self.nrew += 1
            self.mean += (x - self.mean) / min(self.nrew, 40)
            self.S[self.cur] += (x - self.mean) / self.prob
        except Exception:
            pass


if __name__ == "__main__":
    run(Bot)
