"""betfold (v6-like): bets or raises about 60% postflop, almost never calls, folds about 70% when bet into. Hand strength picks which hands."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
        if tc == 0:
            if e >= 0.50 or r < 0.30:
                return self.size(req, self.rng.uniform(0.45, 0.85))
            return "check"
        legal_raise = "raise" in req["legal_actions"] and self.raises_this_street(req) < 2
        if e >= 0.80 and legal_raise:
            return self.size(req, 0.75)
        if e >= 0.66 and r < 0.30:
            return "call"
        return "fold"


if __name__ == "__main__":
    run(Bot)
