"""Tier 2: Tier 1 + opponent modelling (adjusted thresholds/sizing), with the endgame lock on.

Adjustments (each bounded, all scaled by how far a shrunk stat is from its prior):
  * bluffs scale with the opponent's fold-to-raise (fewer bluffs vs calling stations)
  * vs loose/passive callers: lower value-raise thresholds and bigger value sizes
  * vs aggressive opponents: call a little lighter
  * vs opponents who raise most of the time (any street): shrink the "big bets are strong"
    call penalty (bet_pressure), down to 0 for an always-raise / always-shove bot
Endgame lock: once our match lead is bigger than the most we could lose by check/folding
every remaining hand, we only check/fold (a guaranteed match win). Bot.choose applies it
(bot/lock.py); Tier 2 turns it on with `lock_enabled` / `lock_assume_alternating`.
"""
from __future__ import annotations

from typing import Any, Optional

from bot.brains.tier1 import DEFAULTS as TIER1_DEFAULTS
from bot.brains.tier1 import Tier1Brain
from bot.opponent import DEFAULT_PRIORS

DEFAULTS: dict[str, Any] = dict(TIER1_DEFAULTS)
DEFAULTS.update({
    "prior_k": 15.0,
    "priors": dict(DEFAULT_PRIORS),
    "bluff_scale_max": 2.0,        # bluff_freq x (fold_to_raise / prior), capped
    "value_shift": 0.15,           # raise threshold drop per unit of (vpip - prior)
    "value_size_shift": 0.6,       # size boost per unit of (prior_ftr - ftr)
    "aggr_call_shift": 0.10,       # call margin drop per unit of (aggression - prior)
    "pressure_aggr_from": 0.6,     # all-street aggression above this shrinks bet_pressure...
    "pressure_aggr_shift": 1.0,    # ...to bet_pressure x (1 - shift * excess); 0 = off
    "lock_enabled": True,
    "lock_assume_alternating": True,   # blinds alternate each hand (False = assume BB always)
})


class Tier2Brain(Tier1Brain):
    name = "tier2"
    param_file = "tier2"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)          # Tier 1 builds self.opponent from priors / prior_k
        self.lock_enabled = bool(self.p["lock_enabled"])
        self.lock_assume_alternating = bool(self.p["lock_assume_alternating"])

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}

    def params(self) -> dict[str, Any]:
        """Copy of the parameters, shifted by the opponent model."""
        p = dict(self.p)
        opp = self.opponent
        pri = opp.priors
        ftr, vpip, aggr = opp.get("fold_to_raise"), opp.get("vpip"), opp.get("aggression")
        scale = min(p["bluff_scale_max"], ftr / max(pri["fold_to_raise"], 1e-6))
        p["bluff_freq"] = p["bluff_freq"] * scale
        drop = p["value_shift"] * max(0.0, vpip - pri["vpip"])
        thr = p["raise_equity"]
        p["raise_equity"] = ([t - drop for t in thr] if isinstance(thr, list) else thr - drop)
        boost = 1.0 + p["value_size_shift"] * max(0.0, pri["fold_to_raise"] - ftr)
        p["value_frac"] = p["value_frac"] * boost
        p["call_margin"] = p["call_margin"] - p["aggr_call_shift"] * (aggr - pri["aggression"])
        # Big bets from someone who raises nearly always say little about their hand.
        # Normal bots measure ~0.40-0.45 here, so they keep the full penalty; maniacs ~0.85,
        # always-shove bots ~0.97.
        a_all, start = opp.get("aggression_all"), p["pressure_aggr_from"]
        excess = max(0.0, a_all - start) / max(1e-6, 1.0 - start)       # 0 below start, 1 at always
        p["bet_pressure"] = p["bet_pressure"] * min(1.0, max(0.0, 1.0 - p["pressure_aggr_shift"] * excess))
        return p
