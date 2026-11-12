"""trapper v4: slowplays monsters only against opponents who bet when checked to, only on dry boards where few cards
can beat us; otherwise bets big for value. River check-raise sized to what they call; stricter folds to big bets."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401


class Bot(BaseBot):
    def _scary(self):
        """Cards that could hand them a comeback: flush or straight potential, a paired board."""
        b = self.board
        if board_wet(b):
            return True
        for s in range(4):
            if sum(1 for c in b if c & 3 == s) >= 3:
                return True
        rs = sorted({c >> 2 for c in b})
        return any(rs[i + 2] - rs[i] <= 4 for i in range(len(rs) - 2))

    def _bettor(self):
        return self.opp.bet_rate >= 0.42 or self.opp.chances < 6 and self.opp.bet_rate >= 0.37

    def first_look(self, req, P):
        st, tc = req["street"], req["to_call"]
        if st == "preflop":
            return None
        e = self.eq(req)
        legal_raise = "raise" in req["legal_actions"] and self.raises_this_street(req) < 2
        if tc > 0:
            f = self.bet_frac(req)
            if f > 0.85 and e < 0.80:                                  # fold discipline vs big bets
                need = self.odds(req) + 0.06 + (0.03 if st == "river" else 0.0)
                if e < need:
                    return "fold"
        if e < 0.86:
            return None
        trap = self._bettor() and not self._scary() and not board_paired(self.board)
        if st in ("flop", "turn"):
            if tc == 0:
                if trap and e >= 0.90 and (st == "flop" or e >= 0.93) and self.rng.random() < 0.8:
                    return "check"                                    # slowplay on a dry board
                return self.size(req, 0.75) if legal_raise else None  # else: bet big, deny draws
            if st == "flop" and trap and e >= 0.90 and self.rng.random() < 0.7:
                return "call"                                         # trap: call now, raise the turn
            return None
        if tc > 0:                                                    # river: the check-raise
            if not legal_raise:
                return "call"
            frac = 1.0 if self.opp.call_rate > 0.5 else 0.7
            return self.size(req, frac)
        if not self.opp_acted_this_street(req) and self._bettor() and e >= 0.9 and self.rng.random() < 0.6:
            return "check"
        return self.size(req, 0.8 if self.opp.call_rate > 0.5 else 0.6) if legal_raise else None


if __name__ == "__main__":
    run(Bot)
