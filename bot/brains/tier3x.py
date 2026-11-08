"""Tier 3 + the exploit layer (build map X3): Tier 3's parameters, moved by bot/brains/exploit.py's
counter-moves as the trait tests (X1) and the type posterior (X2) gain confidence. With no evidence
(or `x_enabled: false`) it plays exactly as Tier 3. `stats` counts decisions each move touched."""
from __future__ import annotations

from typing import Any, Optional

from bot.brains.exploit import (EXPLOIT_DEFAULTS, adjust, checkraise_lambda, foldable_lambda,
                                narrow_equity, overfolder_lambda)
from bot.strategy.oppstats import STREET_SPOT
from bot.brains.tier3 import Tier3Brain
from bot.actions import FOLD, RAISE
from bot.log import warn
from bot.state import ME


class Tier3XBrain(Tier3Brain):
    name = "tier3x"
    param_file = "tier3"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)
        self.stats.update({"x_overfolder": 0, "x_valueonly": 0, "x_errors": 0, "x_narrowed": 0, 
                           "x_selfdef": 0, "x_cr": 0})
        self._sd_faced = 0                         # flop/turn bets we faced (decisions), for the self-check
        self._sd_folds = 0                         # ... and folded to
        self._faced: list[float] = []              # size (x pot before the bet) of each river bet we faced
        self._faced_key = None

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        d = Tier3Brain.defaults()
        d.update(EXPLOIT_DEFAULTS)
        # RF's D4 (docs/tier4/handoff/RF.md): river solver + sharp narrowing + RNR vs callers only; plain tier3 keeps it off
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

    def _facing_bet(self, c, s, legal, p):
        """Flop/turn bet to face with `x_selfdef` on: defend wider when we fold too often to a frequent bettor."""
        if p.get("x_selfdef") and c.street in (1, 2):
            try:
                lam = foldable_lambda(p, self._sd_faced, self._sd_folds, self._bet_rate())
                if lam > 0.0:
                    q = dict(p)
                    q["mdf_flop"] = min(1.0, float(p["mdf_flop"]) * (1.0 + float(p["x_sd_mdf"]) * lam))
                    q["mdf_turn"] = min(1.0, float(p["mdf_turn"]) * (1.0 + float(p["x_sd_mdf"]) * lam))
                    q["call_margin"] = float(p["call_margin"]) - float(p["x_sd_margin"]) * lam
                    self.stats["x_selfdef"] += 1
                    p = q
            except Exception as e:
                self.stats["x_errors"] += 1
                warn(f"self-check failed: {e!r}")
        return super()._facing_bet(c, s, legal, p)

    def play(self, s, legal, budget_s, p):
        a = super().play(s, legal, budget_s, p)
        h = s.hand
        if h is not None and h.street in (1, 2) and h.tocall > 0 and not legal.can_special:
            self._sd_faced += 1                   # our own fold rate to flop/turn bets (exact, from hand 1)
            self._sd_folds += int(a.kind == FOLD)
        return a

    def _bet_rate(self) -> float:
        """How often the opponent bets when it may (c-bet and turn bet, shrunk means)."""
        sp = self.opponent.spots.spots
        cb, tb = sp["cbet"], sp["turn_bet"]
        n = cb.n + tb.n
        return (cb.mean() * (cb.n + 1) + tb.mean() * (tb.n + 1)) / (n + 2)

    def _raise_a_bet(self, c, s, legal, p, frac):
        """With `x_cr`: against a frequent bettor that folds to our flop/turn bets, raise its bet more often
        with a hand that has some equity but would not raise on its own (bluff-size raise)."""
        a = super()._raise_a_bet(c, s, legal, p, frac)
        if a is not None or not p.get("x_cr") or c.street not in (1, 2) or not legal.can_raise:
            return a
        if any(r.street == c.street and r.actor == ME and r.action.kind == RAISE for r in c.hand.history):
            return None                           # one raise per street, as Tier 3
        try:
            if not (float(p["x_cr_eq_lo"]) <= c.eq < float(p["x_cr_eq_hi"])):
                return None
            spot = self.opponent.spots.spots[STREET_SPOT[c.street]]
            lam = checkraise_lambda(p, self._bet_rate(), spot.mean(), spot.n)
            if lam > 0.0 and self._chance(float(p["x_cr_prob"]) * lam):
                b = self._size(float(p["raise_frac"]), "bluff", c, s, legal, p)
                if b is not None:
                    self.stats["x_cr"] += 1
                    return b
        except Exception as e:
            self.stats["x_errors"] += 1
            warn(f"check-raise failed: {e!r}")
        return None
