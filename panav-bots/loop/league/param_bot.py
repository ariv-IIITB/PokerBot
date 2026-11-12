"""League param bot: ONE template, behaviour set by a PARAMS dict (see SPACE). Real protocol, stdlib only.

In-repo use needs spar/common.py importable; `make_bot.py PARAMS.json OUT.py` writes a STANDALONE file
(common.py + this body + PARAMS baked in), which is what the duels run.
"""
import os
import sys

# ---- BEGIN-IMPORT (stripped by make_bot.py)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "eval_bots", "spar"))
from common import (BaseBot, run, board_wet, has_draw, pre_pct, range_equity, keep_best_two,  # noqa: E402,F401
                    card_to_int)
# ---- END-IMPORT

# name: (lo, hi, default)   -- all continuous; use_discard is thresholded at 0.5
SPACE = {
    "open": (0.20, 1.00, 0.55),      # preflop: share of hands raised first-in on the button (BB iso-raise = half of it)
    "defend": (0.15, 1.00, 0.60),    # preflop: share of hands that continue (call) vs an open raise as BB
    "three": (0.00, 0.40, 0.10),     # preflop: 3-bet share (top of range) vs an open
    "fold3": (0.00, 1.00, 0.50),     # preflop: fold prob vs a 3-bet for hands outside the top ~10 %
    "bet_f": (0.0, 1.0, 0.6),        # flop: bet freq when aggressor (first in / checked to)
    "bet_t": (0.0, 1.0, 0.5),
    "bet_r": (0.0, 1.0, 0.4),
    "probe": (0.0, 1.0, 0.3),        # bet freq (all streets) when NOT the preflop aggressor and nobody bet
    "size_f": (0.25, 2.5, 0.65),     # bet size, fraction of pot, per street
    "size_t": (0.25, 2.5, 0.7),
    "size_r": (0.25, 2.5, 0.75),
    "bluff": (0.0, 0.8, 0.25),       # share of our bets that are bluffs (weak equity)
    "xr": (0.0, 1.0, 0.1),           # check (trap) strong hands when first to act, then raise
    "raise_bi": (0.0, 1.0, 0.2),     # raise freq when bet into
    "margin": (-0.12, 0.15, 0.02),   # call threshold: equity must beat pot odds by this margin
    "giveup": (0.0, 1.0, 0.4),       # prob. to stop betting weak hands on a street after our bet was called
    "use_discard": (0.0, 1.0, 1.0),  # use the revealed opponent discard when estimating ranges (>=0.5 on)
}
DEFAULTS = {k: v[2] for k, v in SPACE.items()}
PARAMS = {}                          # baked by make_bot.py (missing keys take DEFAULTS)


def _clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self.Q = dict(DEFAULTS)
        self.Q.update(PARAMS)
        self.checked_trap = False
        self.last_street = None

    def on_new_hand(self, msg):
        super().on_new_hand(msg)
        self.checked_trap = False

    def eq(self, req):
        if self._eq is None:
            od = self.opp_discard if self.Q["use_discard"] >= 0.5 else None
            self._eq = range_equity(self.hole, self.board, self.rng, self.pressure(req), od)
        return self._eq

    # ---- preflop
    def preflop(self, req, P):
        Q = self.Q
        pct = pre_pct(self.hole)
        tc, ob = req["to_call"], req["opp_bet"]
        n_r = sum(1 for e in req.get("history", []) if e.get("street") == "preflop" and e.get("action") == "raise")
        r = self.rng.random()
        can_raise = "raise" in req["legal_actions"]
        if ob <= 2:                                              # nobody has raised
            if tc > 0:                                           # button first to act
                if pct >= 1.0 - Q["open"] and can_raise:
                    return ("raise", 6)
                return "call" if pct >= 1.0 - min(1.0, Q["open"] + 0.15) and r < 0.5 else "fold"
            return ("raise", 6) if (pct >= 1.0 - 0.5 * Q["open"] and can_raise) else "check"
        if n_r <= 1:                                             # facing an open raise
            if pct >= 1.0 - Q["three"] and can_raise:
                return ("raise", max(18, 3 * ob))
            return "call" if pct >= 1.0 - Q["defend"] else "fold"
        if n_r == 2:                                             # facing a 3-bet
            if pct >= 0.96 and can_raise:
                return ("raise", max(3 * ob, 40))
            if pct >= 0.90:
                return "call"
            return "fold" if r < Q["fold3"] else "call"
        return "call" if pct >= 0.93 else "fold"

    # ---- postflop
    def postflop(self, req, P):
        Q = self.Q
        st, tc = req["street"], req["to_call"]
        si = ("flop", "turn", "river").index(st)
        e = self.eq(req)
        wet = board_wet(self.board)
        draw = st != "river" and has_draw(self.hole, self.board)
        hist = req.get("history", [])
        legal_raise = "raise" in req["legal_actions"] and self.raises_this_street(req) < 2
        size = (Q["size_f"], Q["size_t"], Q["size_r"])[si]
        r = self.rng.random()
        if tc > 0:                                               # facing a bet
            R = {"flop": 0.90, "turn": 0.94, "river": 1.0}[st] + (0.03 if self.in_position() else 0.0)
            need = self.odds(req) / min(1.0, R) + Q["margin"]
            if legal_raise:
                if e >= 0.78:
                    p = _clamp(0.30 + Q["raise_bi"] + (0.4 if self.checked_trap else 0.0))
                    if r < p:
                        return self.size(req, max(0.5, size))
                elif (e < 0.30 or (draw and e < 0.5)) and r < Q["raise_bi"] * Q["bluff"] * 0.7:
                    return self.size(req, max(0.5, size))
            return "call" if e >= need else "fold"
        # no bet to face: bet or check
        aggressor = self.preflop_raiser(req) == "me"
        f = (Q["bet_f"], Q["bet_t"], Q["bet_r"])[si] if aggressor else Q["probe"]
        prev_bet_called = any(x.get("actor") == "me" and x.get("action") == "raise" and x.get("street") != st
                              for x in hist)
        b = Q["bluff"]
        first = not self.opp_acted_this_street(req)
        if e >= 0.58:                                            # value region
            pv = _clamp(f * (1.0 - b) / 0.4)
            if e >= 0.78 and first and r < Q["xr"]:
                self.checked_trap = True
                return "check"
            if self.rng.random() < pv:
                return self.size(req, size)
            return "check"
        if e < 0.45 or (draw and e < 0.55):                      # weak region: bluffs
            pb = _clamp(f * b / 0.4)
            if prev_bet_called:
                pb *= (1.0 - Q["giveup"])
            if self.rng.random() < pb:
                return self.size(req, size)
            return "check"
        pm = _clamp(f - 0.5)                                     # middle: only very aggressive styles bet
        if prev_bet_called:
            pm *= (1.0 - Q["giveup"])
        return self.size(req, size) if self.rng.random() < pm else "check"


# ---- BEGIN-MAIN
if __name__ == "__main__":
    run(Bot)
# ---- END-MAIN
