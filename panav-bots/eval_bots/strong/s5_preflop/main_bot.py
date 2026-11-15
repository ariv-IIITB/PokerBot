"""s5_preflop: percentile preflop policy tuned by position (button opens wide, big blind defends by pot odds,
3-bet/4-bet ladders), then equity-vs-range postflop from the shared core."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run, pre_pct  # noqa: E402

P5 = dict(BASE)
P5.update(
    open=0.17, limp=0.05, defend=0.27, three=0.86, three_bluff=0.12, call3=0.52, four=0.96, call4=0.90,
    bb_raise=0.55, open_to=5, three_to=16,
)


class Bot(BaseBot):
    P = P5

    def preflop(self, req, P):
        pct = pre_pct(self.hole)
        tc, ob = req["to_call"], req["opp_bet"]
        n_r = sum(1 for e in req.get("history", []) if e.get("street") == "preflop" and e.get("action") == "raise")
        r = self.rng.random()
        if ob <= 2:
            if tc > 0:                                   # button, first to act
                if pct >= P["open"]:
                    return ("raise", P["open_to"])
                if pct >= P["limp"] and r < 0.5:
                    return "call"
                return "fold"
            return ("raise", 7 if pct >= 0.80 else P["open_to"] + 1) if pct >= P["bb_raise"] else "check"
        if n_r <= 1:
            # price: facing a raise to ob, we call (ob - my_bet) into pot 2*ob; big blind has price, button limp-raise rare
            size_up = ob / 2.0
            d = P["defend"] + 0.03 * max(0.0, size_up - 2.5)      # defend a bit tighter vs bigger opens
            if pct >= P["three"] or (P["three_bluff"] and 0.30 <= pct < 0.55 and r < P["three_bluff"]):
                return ("raise", max(P["three_to"], 3 * ob))
            return "call" if pct >= d else "fold"
        if n_r == 2:
            if pct >= P["four"]:
                return ("raise", max(3 * ob, 40))
            return "call" if pct >= P["call3"] + 0.03 * (ob > 24) else "fold"
        return "call" if pct >= P["call4"] else "fold"


if __name__ == "__main__":
    run(Bot)
