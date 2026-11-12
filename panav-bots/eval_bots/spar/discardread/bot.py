"""discardread: reads our exposed discard (a high card thrown suggests a pair or suited cards kept) and bluffs more when the board misses that guess."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401



class Bot(BaseBot):
    def params(self):
        od = self.opp_discard
        if od is not None and (od >> 2) >= 9 and self.board and not board_wet(self.board) and not board_paired(self.board):
            return dict(BASE, semi=0.7, river_bluff=0.40, cbet=1.0)       # the board misses a pair / suited guess
        return BASE


if __name__ == "__main__":
    run(Bot)
