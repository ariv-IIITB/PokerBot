"""polar (v4): polarised 2x-pot overbets. Bluffs chosen with blockers / draws, frequency driven by the opponent's observed
fold rate; against stations it drops bluffs and bets thin value at smaller sizes."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401


def blocks_nuts(hole, board):
    """Holds an ace, or the highest card of a suit that has 3+ on the board (nut-flush blocker)."""
    if any(c >> 2 == 12 for c in hole):
        return True
    for s in range(4):
        if sum(1 for c in board if c & 3 == s) >= 3:
            if any(c & 3 == s and c >> 2 >= 10 for c in hole):
                return True
    return False


class Bot(BaseBot):
    def first_look(self, req, P):
        if req["street"] == "preflop" or req["to_call"] > 0:
            return None
        opp = self.opp
        st = req["street"]
        e = self.eq(req)
        known = opp.faced >= 6
        fold = opp.fold_rate
        station = known and fold < 0.25
        if e >= 0.80:
            return self.size(req, 1.0 if station else 2.0)
        if station:
            # no bluffs; thin value in small sizes
            if e >= 0.62:
                return self.size(req, 0.6)
            return "check"
        if opp.call_rate > 0.6 and e >= 0.68:
            return self.size(req, 0.6)
        draw = st != "river" and has_draw(self.hole, self.board)
        blk = blocks_nuts(self.hole, self.board)
        weak = (e <= 0.25) if st == "river" else (e <= 0.22)
        if not (weak or draw):
            return "check"
        # overbet bluff needs folds ~40%: scale by observed fold rate
        f = min(1.6, fold / 0.40)
        p = 0.50 * f
        if weak and blk:
            p *= 1.5
        elif weak and st == "river" and e > 0.12:
            p *= 0.6                                    # has some showdown value, rather check
        if draw and not weak:
            p *= 0.9
        if self.rng.random() < min(0.9, p):
            return self.size(req, 2.0 if fold >= 0.35 else 1.0)
        return "check"


if __name__ == "__main__":
    run(Bot)
