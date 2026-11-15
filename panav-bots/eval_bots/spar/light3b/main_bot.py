"""light3b: opens wide, 3-bets about 40% preflop (value plus bluffs), c-bets every flop, gives up on the turn without equity or a draw."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401

P = dict(BASE, open=0.22, three=0.62, three_bluff=0.30, defend=0.30, cbet=1.0)


class Bot(BaseBot):
    P = P

    def first_look(self, req, P):
        st, tc = req["street"], req["to_call"]
        if st == "preflop":
            return None
        e = self.eq(req)
        if st == "flop" and tc == 0:
            return self.size(req, 0.55)                               # c-bet every flop
        if st == "turn" and tc == 0 and e < 0.45 and not has_draw(self.hole, self.board):
            return "check"                                            # gives up
        return None


if __name__ == "__main__":
    run(Bot)
