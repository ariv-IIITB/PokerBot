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

from bot.actions import RAISE, Action, LegalActions, pot_fraction_raise, safe_action
from bot.brains.tier1 import DEFAULTS as TIER1_DEFAULTS
from bot.brains.tier1 import Tier1Brain
from bot.situation import lock_margin  # noqa: F401  (re-exported: tests, lab)
from bot.opponent import DEFAULT_PRIORS
from bot.state import GameState
from bot.strategy.oppstats import OppStats

DEFAULTS: dict[str, Any] = dict(TIER1_DEFAULTS)
DEFAULTS.update({
    "prior_k": 15.0,
    "priors": dict(DEFAULT_PRIORS),
    "bluff_scale_max": 2.0,        # bluff_freq x (fold_to_raise / prior), capped
    "adapt_bluffs": True,          # False: bluff_freq stays at its Tier 1 value (ablation switch)
    "value_shift": 0.15,           # raise threshold drop per unit of (vpip - prior)
    "value_size_shift": 0.6,       # size boost per unit of (prior_ftr - ftr)
    "aggr_call_shift": 0.0,        # call margin drop per unit of (aggression - prior); 0.10 cost ~0.6 vs tier1/opp4 (Phase F0), off
    "pressure_aggr_from": 0.6,     # all-street aggression above this shrinks bet_pressure...
    "pressure_aggr_shift": 1.0,    # ...to bet_pressure x (1 - shift * excess); 0 = off
    "lock_enabled": True,
    "lock_assume_alternating": True,   # blinds alternate each hand (False = assume BB always)
    # E3/E4: per-spot opponent stats (bot/strategy/oppstats.py) and the river bluff-catch rule
    "oppstats_strength": 15.0,     # prior worth this many observations
    "oppstats_gate": 20,           # a spot moves play only after this many samples...
    "oppstats_cap": 0.15,          # ...and by at most this much
    "weak_below": 0.5,             # a shown bet hand below this percentile counts as a bluff
    # E5/E6: bet sizes by expected value, and no awkward leftovers (both off until they pass the keep rule)
    "ev_sizing": False,            # choose the size among ev_fracs + all-in by EV with measured fold rates
    "ev_fracs": [0.33, 0.66, 1.1], # candidate sizes, x (pot + call)
    "ev_called_discount": 0.10,    # our equity when called = equity - discount x size (a call is informative)
    "ev_margin": 0.04,             # sizes within this x pot of the best EV are picked by a seeded draw
    "leftover_frac": 0.0,          # a value raise leaving less than this share of the new pot behind shoves (0 = off)
    "river_bluff_slope": 0.5,      # (E4 kept) extra equity needed to call a turn/river bet, per point the
    "bluff_ref": 0.22,             # bluff index sits below this (0 slope = the old rule)
})


def raise_fraction(action: Action, h) -> float:
    """Our bet or raise as a fraction of the pot we were betting into (pot + what we call)."""
    extra = int(action.amount) - (h.my_bet or 0) - h.tocall
    return max(0.0, extra / max(1, h.pot + h.tocall))


class Tier2Brain(Tier1Brain):
    name = "tier2"
    param_file = "tier2"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)            # builds self.opponent with our priors
        self.opponent.spots = OppStats(strength=float(self.p["oppstats_strength"]),
                                       gate=int(self.p["oppstats_gate"]), cap=float(self.p["oppstats_cap"]),
                                       weak_below=float(self.p["weak_below"]))
        self.locked_decisions = 0

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}

    def adjusted(self, street: int = 0) -> dict[str, Any]:
        """Copy of the parameters, shifted by the opponent model. `street`: the street of the
        decision (the river bluff-catch rule applies from the turn on)."""
        p = dict(self.p)
        opp = self.opponent
        pri = opp.priors
        ftr, vpip, aggr = opp.get("fold_to_raise"), opp.get("vpip"), opp.get("aggression")
        scale = min(p["bluff_scale_max"], ftr / max(pri["fold_to_raise"], 1e-6))
        if p["adapt_bluffs"]:
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
        if street >= 2:
            # Bluff-catching: a value-heavy bettor (low bluff index) is called less, an
            # over-bluffer more. The prior is value-heavy, so the default is stricter than before.
            p["call_margin"] += p["river_bluff_slope"] * (p["bluff_ref"] - opp.spots.bluff_index())
        return p

    # ---- sizing (E5, E6)
    def sized_raise(self, frac, kind, eq, state, legal, p):
        h = state.hand
        assert h is not None
        a = super().sized_raise(frac, kind, eq, state, legal, p)
        if a is None:
            return None
        if p["ev_sizing"] and h.street >= 1:
            a = self.ev_size(a, kind, eq, h, legal, p)
        if kind == "value" and p["leftover_frac"] > 0:
            a = self.no_leftovers(a, h, legal, p["leftover_frac"])
        return a

    def ev_size(self, default: Action, kind: str, eq: float, h, legal, p) -> Action:
        """The candidate size with the best expected chips: fold equity from the measured
        fold rates (oppstats), the rest of the time we are called with a somewhat worse
        hand than we hold. Near-ties are drawn at random so sizes do not give the hand away."""
        pot, to_call, mybet = h.pot, h.tocall, h.my_bet or 0
        amounts = {default.amount}
        for f in p["ev_fracs"]:
            r = pot_fraction_raise(f, pot, to_call, h.my_bet, legal)
            if r is not None:
                amounts.add(r.amount)
        amounts.add(legal.raise_max)
        scored = []
        for amt in sorted(amounts):
            extra = amt - mybet - to_call                     # chips added beyond the call
            if extra <= 0:
                continue
            size = extra / max(1, pot + to_call)
            pf = self.opponent.spots.fold_prob(size, h.street)
            eq_called = max(0.0, eq - p["ev_called_discount"] * size)
            ev = pf * pot + (1 - pf) * (eq_called * (pot + to_call + 2 * extra) - (to_call + extra))
            scored.append((ev, amt))
        if not scored:
            return default
        best = max(ev for ev, _ in scored)
        near = [amt for ev, amt in scored if ev >= best - p["ev_margin"] * pot]
        return Action.raise_to(near[int(self.pyrng.random() * len(near)) % len(near)])

    @staticmethod
    def no_leftovers(a: Action, h, legal, frac: float) -> Action:
        """A raise that leaves less than `frac` of the new pot behind is pointless: go all-in."""
        put_in = int(a.amount) - (h.my_bet or 0)
        behind = h.my_stack - put_in
        if behind > 0 and behind < frac * (h.pot + put_in):
            return Action.raise_to(legal.raise_max)
        return a

    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        s = self.situation(state)
        if s.locked():
            self.locked_decisions += 1
            if legal.can_special:           # a discard puts no chips in: play it normally
                return s.special(legal, budget_s)
            return safe_action(legal)
        h = s.hand
        action = self.play(s, legal, budget_s, self.adjusted(h.street if h is not None else 0))
        if action.kind == RAISE and h is not None:  # the opponent's next action answers this bet
            self.opponent.spots.note_raise(h.street, raise_fraction(action, h))
        return action
