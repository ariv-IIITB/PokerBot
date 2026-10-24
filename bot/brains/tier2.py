"""Tier 2: Tier 1 + opponent modelling, adjusted thresholds/sizing, and the endgame lock.

Adjustments (each bounded, all scaled by how far a shrunk stat is from its prior):
  * bluffs scale with the opponent's fold-to-raise (fewer bluffs vs calling stations)
  * vs loose/passive callers: lower value-raise thresholds and bigger value sizes
  * vs aggressive opponents: call a little lighter
Endgame lock: once our match lead is bigger than the most we could lose by check/folding
every remaining hand, we only check/fold (a guaranteed match win). See `lock_margin`.
"""
from __future__ import annotations

from typing import Any, Optional

from bot.actions import Action, LegalActions, safe_action
from bot.brains.tier1 import DEFAULTS as TIER1_DEFAULTS
from bot.brains.tier1 import Tier1Brain
from bot.opponent import DEFAULT_PRIORS, OpponentModel
from bot.protocol import Message
from bot.state import GameState

DEFAULTS: dict[str, Any] = dict(TIER1_DEFAULTS)
DEFAULTS.update({
    "prior_k": 15.0,
    "priors": dict(DEFAULT_PRIORS),
    "bluff_scale_max": 2.0,        # bluff_freq x (fold_to_raise / prior), capped
    "value_shift": 0.15,           # raise threshold drop per unit of (vpip - prior)
    "value_size_shift": 0.6,       # size boost per unit of (prior_ftr - ftr)
    "aggr_call_shift": 0.10,       # call margin drop per unit of (aggression - prior)
    "lock_enabled": True,
    "lock_assume_alternating": True,   # blinds alternate each hand (False = assume BB always)
})


def lock_margin(state: GameState, assume_alternating: bool = True) -> Optional[int]:
    """Lead minus the worst-case loss from check/folding the rest of the match.

    Worst case = what we've already put in this hand (lost if we fold now) + the blind we
    post in every future hand. Our seat alternates each hand (seat 0 = small blind), as in
    a duplicate match; with assume_alternating=False every future hand costs a big blind.
    > 0 means the match is mathematically won by check/folding. None if unknown.
    """
    h, m = state.hand, state.match
    if h is None or h.finished:
        return None
    committed = h.start_stack - h.my_stack
    future = max(0, m.hands - state.hands_played - 1)
    if assume_alternating:
        # Future hand j (1..future) has seat (seat + j) % 2.
        sb_hands = sum(1 for j in range(1, future + 1) if (h.seat + j) % 2 == 0)
        cost = sb_hands * m.sb + (future - sb_hands) * m.bb
    else:
        cost = future * max(m.sb, m.bb)
    return state.bankroll - committed - cost


class Tier2Brain(Tier1Brain):
    name = "tier2"
    param_file = "tier2"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)
        priors = dict(DEFAULT_PRIORS)
        priors.update(self.p.get("priors") or {})
        self.opp = OpponentModel(priors=priors, k=float(self.p["prior_k"]))
        self.locked_decisions = 0

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}

    def observe(self, state: GameState, msg: Message) -> None:
        self.opp.update(state, msg)

    def adjusted(self) -> dict[str, Any]:
        """Copy of the parameters, shifted by the opponent model."""
        p = dict(self.p)
        pri = self.opp.priors
        ftr, vpip, aggr = (self.opp.get("fold_to_raise"), self.opp.get("vpip"),
                           self.opp.get("aggression"))
        scale = min(p["bluff_scale_max"], ftr / max(pri["fold_to_raise"], 1e-6))
        p["bluff_freq"] = p["bluff_freq"] * scale
        drop = p["value_shift"] * max(0.0, vpip - pri["vpip"])
        thr = p["raise_equity"]
        p["raise_equity"] = ([t - drop for t in thr] if isinstance(thr, list) else thr - drop)
        boost = 1.0 + p["value_size_shift"] * max(0.0, pri["fold_to_raise"] - ftr)
        p["value_frac"] = p["value_frac"] * boost
        p["call_margin"] = p["call_margin"] - p["aggr_call_shift"] * (aggr - pri["aggression"])
        return p

    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        if self.p["lock_enabled"]:
            margin = lock_margin(state, bool(self.p["lock_assume_alternating"]))
            if margin is not None and margin > 0:
                self.locked_decisions += 1
                return safe_action(legal)
        if legal.can_special:
            return Action.special(legal.special.choices[0])  # type: ignore[union-attr]
        h = state.hand
        if h is None or not h.hole:
            return safe_action(legal)
        eq = self.equity(state, budget_s)
        return self.choose(state, legal, eq, self.adjusted())
