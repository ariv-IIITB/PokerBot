"""Tier 3 + the exploit layer (build map X3): Tier 3's parameters, moved by bot/brains/exploit.py's
counter-moves as the trait tests (X1) and the type posterior (X2) gain confidence. With no evidence
(or `x_enabled: false`) it plays exactly as Tier 3. `stats` counts decisions each move touched."""
from __future__ import annotations

from typing import Any, Optional

from bot.brains.exploit import EXPLOIT_DEFAULTS, adjust
from bot.brains.tier3 import Tier3Brain
from bot.log import warn


class Tier3XBrain(Tier3Brain):
    name = "tier3x"
    param_file = "tier3"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)
        self.stats.update({"x_overfolder": 0, "x_valueonly": 0, "x_errors": 0})

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
        return q
