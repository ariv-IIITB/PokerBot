"""Tier 2: Tier 1 + opponent modelling, adjusted thresholds/sizing, and the endgame lock.

Adjustments (each bounded, all scaled by how far a shrunk stat is from its prior):
  * bluffs scale with the opponent's fold-to-raise (fewer bluffs vs calling stations)
  * vs loose/passive callers: lower value-raise thresholds and bigger value sizes
  * vs aggressive opponents: call a little lighter
  * vs opponents who raise most of the time (any street): shrink the "big bets are strong"
    call penalty (bet_pressure), down to 0 for an always-raise / always-shove bot
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
    "pressure_aggr_from": 0.6,     # all-street aggression above this shrinks bet_pressure...
    "pressure_aggr_shift": 1.0,    # ...to bet_pressure x (1 - shift * excess); 0 = off
    "lock_enabled": True,
    "lock_assume_alternating": True,   # blinds alternate each hand (False = assume BB always)
})


def lock_margin(state: GameState, assume_alternating: bool = True, rules=None) -> Optional[int]:
    """Lead minus the worst-case loss from check/folding the rest of the match.

    Worst case = what we've already put in this hand (lost if we fold now) + the forced
    bets we post in every future hand (ante + our blind, or the straddle). Our seat
    alternates each hand (seat 0 = small blind), as in a duplicate match; with
    assume_alternating=False every future hand costs the bigger forced bet. Blind
    schedules come from `rules` (the compiled variant) when known.
    > 0 means the match is mathematically won by check/folding. None if unknown.
    """
    h, m = state.hand, state.match
    if h is None or h.finished:
        return None
    committed = h.start_stack - h.my_stack
    future = max(0, m.hands - state.hands_played - 1)
    first_future = h.hand_id + 1

    def costs(j: int) -> tuple[int, int]:
        """(small-blind seat cost, big-blind seat cost) for future hand j."""
        if rules is not None and hasattr(rules, "level_at"):
            sb, bb, ante, straddle = rules.level_at(first_future + j - 1)
        else:
            sb = h.sb if h.sb is not None else m.sb
            bb = h.bb if h.bb is not None else m.bb
            ante, straddle = h.ante or 0, 0
        return ante + (straddle or sb), ante + bb

    cost = 0
    for j in range(1, future + 1):
        sb_cost, bb_cost = costs(j)
        if assume_alternating:
            cost += sb_cost if (h.seat + j) % 2 == 0 else bb_cost
        else:
            cost += max(sb_cost, bb_cost)
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
        super().observe(state, msg)
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
        # Big bets from someone who raises nearly always say little about their hand.
        # Normal bots measure ~0.40-0.45 here, so they keep the full penalty; maniacs ~0.85,
        # always-shove bots ~0.97.
        a_all, start = self.opp.get("aggression_all"), p["pressure_aggr_from"]
        excess = max(0.0, a_all - start) / max(1e-6, 1.0 - start)       # 0 below start, 1 at always
        p["bet_pressure"] = p["bet_pressure"] * min(1.0, max(0.0, 1.0 - p["pressure_aggr_shift"] * excess))
        return p

    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        if self.p["lock_enabled"]:
            margin = lock_margin(state, bool(self.p["lock_assume_alternating"]), self.rules)
            if margin is not None and margin > 0:
                self.locked_decisions += 1
                return safe_action(legal)
        if legal.can_special:
            return self.special(state, legal, budget_s)
        h = state.hand
        if h is None or not h.hole:
            return safe_action(legal)
        eq = self.equity(state, budget_s)
        return self.choose(state, legal, eq, self.adjusted())
