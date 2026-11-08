"""Tier 3 + the exploit layer (build map X3): Tier 3's parameters, moved by bot/brains/exploit.py's
counter-moves as the trait tests (X1) and the type posterior (X2) gain confidence. With no evidence
(or `x_enabled: false`) it plays exactly as Tier 3. `stats` counts decisions each move touched."""
from __future__ import annotations

from typing import Any, Optional

from bot.brains.exploit import EXPLOIT_DEFAULTS, adjust, narrow_equity
from bot.brains.tier3 import Tier3Brain
from bot.log import warn


class Tier3XBrain(Tier3Brain):
    name = "tier3x"
    param_file = "tier3"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)
        self.stats.update({"x_overfolder": 0, "x_valueonly": 0, "x_errors": 0, "x_narrowed": 0})
        self._faced: list[float] = []              # size (x pot before the bet) of each river bet we faced
        self._faced_key = None

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        d = Tier3Brain.defaults()
        d.update(EXPLOIT_DEFAULTS)
        # RF's D4 (docs/archive/tier4/handoff/RF.md): river solver + sharp narrowing + RNR vs callers only; plain tier3 keeps it off
        d.update({"t3_river_solver": True, "t3_river_narrow": True, "narrow_n0": 0.001, "t3_river_rnr": True,
                  "rnr_pmax": 0.9, "rnr_n0": 10, "rnr_min_n": 10, "rnr_dir": -1})
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
        return q

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
