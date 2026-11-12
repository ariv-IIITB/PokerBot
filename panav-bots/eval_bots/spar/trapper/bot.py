"""trapper: slowplays monsters on the flop and turn (dry boards), check-raises the river; weak hands fold to big bets."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401


class Bot(BaseBot):
    def first_look(self, req, P):
        st, tc = req["street"], req["to_call"]
        if st == "preflop":
            return None
        e = self.eq(req)
        if e < 0.86:
            return None
        legal_raise = "raise" in req["legal_actions"] and self.raises_this_street(req) < 2
        if st in ("flop", "turn"):
            if tc == 0:
                if not board_wet(self.board) and self.rng.random() < 0.75:
                    return "check"                                    # slowplay on a dry board
                return None
            if not board_wet(self.board) and self.rng.random() < 0.7:
                return "call"                                         # trap: call now, raise later
            return None
        if tc > 0:                                                    # river: the check-raise
            return self.size(req, 1.0) if legal_raise else "call"
        return "check" if not self.opp_acted_this_street(req) and self.rng.random() < 0.6 else None


if __name__ == "__main__":
    run(Bot)
