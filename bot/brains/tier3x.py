"""Tier 3 + the exploit layer (build map X3): Tier 3's parameters, moved by bot/brains/exploit.py's
counter-moves as the trait tests (X1) and the type posterior (X2) gain confidence. With no evidence
(or `x_enabled: false`) it plays exactly as Tier 3. `stats` counts decisions each move touched."""
from __future__ import annotations

from typing import Any, Optional

from bot.brains.exploit import (EXPLOIT_DEFAULTS, adjust, narrow_equity, overfolder_lambda, stab_prob,
                                tight3_lambda)
from bot.strategy.oppstats import STREET_SPOT
from bot.brains.tier3 import Tier3Brain
from bot.actions import RAISE
from bot.state import ME
from bot.log import warn


class Tier3XBrain(Tier3Brain):
    name = "tier3x"
    param_file = "tier3"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)
        self.stats.update({"x_overfolder": 0, "x_valueonly": 0, "x_errors": 0, "x_narrowed": 0, "x_stabs": 0,
                           "x_3b_floor": 0})
        self._faced: list[float] = []              # size (x pot before the bet) of each river bet we faced
        self._faced_key = None

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        d = Tier3Brain.defaults()
        d.update(EXPLOIT_DEFAULTS)
        return d

    def adjusted(self, street: int = 0) -> dict[str, Any]:
        p = super().adjusted(street)
        info: dict = {}
        try:
            q = adjust(p, street, self.opponent.traits, self.opponent.types, info)
        except Exception as e:                    # the layer must never cost a hand: Tier 3's params
            self.stats["x_errors"] += 1
            warn(f"exploit layer failed: {e!r}")
            return p
        self.stats["x_overfolder"] += int(info.get("overfolder", 0.0) > 0)
        self.stats["x_valueonly"] += int(info.get("valueonly", 0.0) > 0 and street == 3)
        lam = self._tight3(p) if street == 0 else 0.0
        if lam > 0:
            q = dict(q)
            c = float(q["pf_btn_continue"])
            q["pf_btn_continue"] = c - lam * max(0.0, c - float(p["x_3b_min"]))
        return q

    def _tight3(self, p: dict) -> float:
        return tight3_lambda(self.opponent.spots.spots["three_bet"].mean(), float(p.get("x_3b_ref", 0.0)))

    def choose(self, state, legal, eq: float, p: dict):
        """Facing a river bet with `x_narrow` on: the equity is re-read against the bettor's betting range."""
        h = state.hand
        if p.get("x_narrow") and h is not None and h.street == 3 and h.tocall > 0:
            try:
                eq, p = self._narrowed(h, eq, p)
                self.stats["x_narrowed"] += 1
            except Exception as e:
                self.stats["x_errors"] += 1
                warn(f"range narrowing failed: {e!r}")
        return super().choose(state, legal, eq, p)

    def t2_calls(self, h, eq: float, p: dict) -> bool:
        """Tier 2's pot-odds rule; facing a re-raise of our preflop raise by a tight 3-bettor (`x_3b_ref`), the
        equity moves from the share vs a random hand toward the share vs the top-30 % table."""
        if h.street == 0 and float(p.get("x_3b_ref", 0.0)) > 0 and reraised(h):
            try:
                t, lam = self.perception.tables, self._tight3(p)
                if lam > 0 and t is not None and t.eq_range is not None:
                    top = float(t.eq_range[t.classes.class_of(h.hole)])
                    eq = min(eq, eq - lam * (eq - top))
                    self.stats["x_3b_floor"] += 1
            except Exception as e:
                self.stats["x_errors"] += 1
                warn(f"re-raise floor failed: {e!r}")
        return Tier3Brain.t2_calls(h, eq, p)

    def _narrowed(self, h, eq: float, p: dict):
        ratio = h.tocall / max(1, h.pot - h.tocall)
        key = (h.hand_id, len(h.history))
        if key != self._faced_key:                 # one entry per bet, however often we are asked
            self._faced_key = key
            self._faced.append(ratio)
        n = len(self._faced)
        k = float(p["x_narrow_k"])
        rank = (sum(1 for r in self._faced if r >= ratio) + 0.5 * k) / (n + k)
        spots = self.opponent.spots
        q = dict(p)
        q["bet_pressure"] = float(p["bet_pressure"]) * float(p["x_narrow_bp"])
        return narrow_equity(eq, spots.spots["river_bet"].mean(), spots.spots["bluff_index"].mean(),
                             rank, float(p["x_narrow_lam"])), q

    def _unfaced(self, c, s, legal, p):
        """Nothing to call, Tier 3 would check: with `x_stab` and an over-folder verdict, bet weak hands
        at the rate the opponent's measured fold rate on this street pays."""
        a = super()._unfaced(c, s, legal, p)
        if not p.get("x_stab") or c.street not in STREET_SPOT or not legal.can_raise or c.eq >= float(p["x_stab_eq"]):
            return a
        if a is not None and a.kind == RAISE:
            return a
        try:
            lam = overfolder_lambda(self.opponent.traits, p["x_ramp"])
            if lam > 0.0:
                fold = self.opponent.spots.spots[STREET_SPOT[c.street]].mean()
                if self._chance(stab_prob(fold, float(p["x_stab_size"]), lam, float(p["x_stab_span"]))):
                    b = self._size(float(p["x_stab_size"]), "bluff", c, s, legal, p)
                    if b is not None:
                        self.stats["x_stabs"] += 1
                        return b
        except Exception as e:
            self.stats["x_errors"] += 1
            warn(f"stab failed: {e!r}")
        return a


def reraised(h) -> bool:
    """We raised preflop and the opponent raised after it."""
    ours = False
    for r in h.history:
        if r.street == 0 and r.action.kind == RAISE:
            if r.actor == ME:
                ours = True
            elif ours:
                return True
    return False
