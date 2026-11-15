"""light3b: opens wide, 3-bets about 40% preflop (value plus bluffs), c-bets every flop, gives up on the turn without equity or a draw."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401

P = dict(BASE, open=0.22, three=0.62, three_bluff=0.30, defend=0.30, cbet=1.0)


class Bot(BaseBot):
    P = P

    @staticmethod
    def bluff_quality(hole):
        """0..3: ace blocker, suitedness, connectedness of the hand (good 3-bet bluffs)."""
        q = 0
        rs = sorted({c >> 2 for c in hole})
        if 12 in rs:
            q += 1
        if max(sum(1 for c in hole if c & 3 == s) for s in range(4)) >= 2:
            q += 1
        if any(b - a <= 2 for a, b in zip(rs, rs[1:])):
            q += 1
        return q

    def first_look(self, req, P):
        st, tc = req["street"], req["to_call"]
        opp = self.opp
        if st == "preflop":
            ob = req["opp_bet"]
            n_r = sum(1 for e in req.get("history", []) if e.get("street") == "preflop" and e.get("action") == "raise")
            if ob > 2 and n_r == 1 and "raise" in req["legal_actions"]:
                pct = pre_pct(self.hole)
                if pct >= P["three"]:
                    return None
                if 0.28 <= pct < 0.60:
                    q = self.bluff_quality(self.hole)
                    pr = (0.08, 0.30, 0.50, 0.65)[q] * min(1.4, max(0.5, opp.fold_rate / 0.35))
                    if self.rng.random() < pr:
                        to = max(P["three_to"], 3 * ob) if self.in_position() else max(P["three_to"] + 2, 3 * ob + 2)
                        return ("raise", to)
                    return "call" if pct >= P["defend"] and q >= 1 else "fold"
            return None
        e = self.eq(req)
        draw = st != "river" and has_draw(self.hole, self.board)
        wet = board_wet(self.board)
        if st == "flop" and tc == 0:
            if e < 0.40 and not draw and opp.faced >= 8 and opp.fold_rate < 0.22 and self.rng.random() < 0.5:
                return "check"                                        # station: stop bluffing air half the time
            return self.size(req, 0.62 if wet else 0.45)              # c-bet every flop, sized by texture
        if st == "turn" and tc == 0 and e < 0.45 and not draw:
            hi = max(c >> 2 for c in self.board[:3])
            scare = self.board[3] >> 2 > hi or (self.board[3] >> 2) == 12
            if scare and self.preflop_raiser(req) == "me" and self.rng.random() < 0.45 * min(1.4, opp.fold_rate / 0.35):
                return self.size(req, 0.6)                            # double barrel on a scare card
            return "check"                                            # gives up
        return None


if __name__ == "__main__":
    run(Bot)
