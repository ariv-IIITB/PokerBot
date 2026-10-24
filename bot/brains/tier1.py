"""Tier 1: expected showdown share vs pot odds, raise thresholds, randomized bluffs, and
generic simulation-based policies for every special step.

Per betting decision:
  1. equity = expected showdown share from here (bot/sim: rebuild the hand from what we've
     seen, sample the hidden cards, check down; handles hi-lo, several boards, wild cards
     and card steps still to come). Cached while the cards we know don't change.
     Fallback: plain MC equity vs a random hand.
  2. equity >= raise threshold for this street -> value raise (pot-fraction sizing)
  3. nobody has bet, weak hand, not preflop -> bluff with probability bluff_freq
  4. facing a bet: call if equity >= pot odds + margin (+ pressure for big bets)
  5. otherwise check if free, else fold
Special steps (discard, draw, swap, choose, bids, quotes, ...) use bot/sim/policies.py.
All numbers live in bot/config/tier1.json (built-in defaults if the file is missing).
"""
from __future__ import annotations

import random
from typing import Any, Optional

import numpy as np

from bot.actions import RAISE, Action, LegalActions, pot_fraction_raise, safe_action
from bot.brains.base import Brain
from bot.brains.params import load_params, per_street
from bot.equity import equity
from bot.log import warn
from bot.protocol import MatchInfo, Message, Showdown
from bot.state import ME, GameState
from bot.game.rules_spec import active_rules, to_rules
from bot.sim.inference import Inference, Trust
from bot.sim.policies import decide_special
from bot.sim.replay import reconstruct
from bot.sim.share import expected_share
from bot.sim.tables import load_tables

DEFAULTS: dict[str, Any] = {
    "seed": 12345,
    "equity_budget_frac": 0.7,     # share of the decision budget spent on equity
    "max_samples": 3000,
    "raise_equity": [0.70, 0.68, 0.70, 0.74],   # per street; last value repeats
    "strong_equity": 0.85,         # use the big size above this
    "value_frac": 0.66,            # value raise size, x pot
    "strong_frac": 1.0,
    "max_own_raises": 2,           # per street, unless equity >= strong_equity
    "call_margin": 0.02,           # call if equity >= pot odds + margin + pressure
    "bet_pressure": 0.10,          # extra equity needed per (to_call / pot)
    "bluff_freq": 0.10,
    "bluff_max_equity": 0.40,
    "bluff_frac": 0.5,
    "special_budget_frac": 0.8,    # share of the budget for special-step policies
    "use_sim": True,               # False: old equity only (and first option for specials)
    "rollout_worlds": 2000,        # caps (the time budget usually binds first)
    "pimc_worlds": 400,
    "inference": True,             # weight opponent hands by their visible choices
    "inference_beta": 6.0,
    "inference_gamma": 3.0,
    "inference_trust": True,       # scale inference by how well it predicted past showdowns
    "use_tables": True,            # precomputed start-of-hand shares, if valid data exists
}


class Tier1Brain(Brain):
    name = "tier1"
    param_file = "tier1"

    def __init__(self, config: Optional[dict] = None, game=None, config_dir=None) -> None:
        self.p = load_params(self.param_file, self.defaults(), config, config_dir)
        # `game`: GameConfig, VariantSpec or Rules; default = the bot's active variant.
        self.rules = to_rules(game) if game is not None else active_rules()
        self.rng = np.random.default_rng(int(self.p["seed"]))
        self.pyrng = random.Random(int(self.p["seed"]))
        self._cache: dict = {}
        self._cache_hand: Optional[int] = None
        self.tables = load_tables(self.rules) if self.p.get("use_tables", True) else None
        self.trust = Trust()
        self._last_rec = None                 # (hand id, Reconstruction) of our last decision
        self.inference = Inference({"enabled": bool(self.p["inference"]),
                                    "beta": float(self.p["inference_beta"]),
                                    "gamma": float(self.p["inference_gamma"]),
                                    "ref_hands": 120, "min_ess": 0.08})

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return dict(DEFAULTS)

    def on_rules(self) -> None:
        self.tables = load_tables(self.rules) if self.p.get("use_tables", True) else None

    # ---- warm-up
    def observe(self, state: GameState, msg: Message) -> None:
        if isinstance(msg, MatchInfo):
            self.warm_up()
        elif isinstance(msg, Showdown) and self.inference.enabled and self.p["inference_trust"]:
            self._score_showdown(state, msg)

    def _score_showdown(self, state: GameState, msg) -> None:
        """Opponent cards revealed: how well did the model explain their decisions?"""
        last = self._last_rec
        if last is None or state.hand is None or last[0] != state.hand.hand_id:
            return
        try:
            self.trust.update(self.inference.decision_llr(last[1], list(msg.oppcards), self.rng))
        except Exception as e:
            warn(f"trust update failed: {e!r}")

    def _apply_trust(self) -> None:
        if self.p["inference_trust"]:
            self.inference.params["gamma"] = float(self.p["inference_gamma"]) * self.trust.level("bet")
            self.inference.params["beta"] = float(self.p["inference_beta"]) * self.trust.level("discard")

    def warm_up(self) -> None:
        """Build evaluator tables and NumPy code paths before the first timed decision
        (the first equity call is ~60 ms, later ones well under 1 ms)."""
        try:
            r = self.rules
            hole = list(r.deck[:r.hole_cards])
            equity(hole, (), r, max_samples=16, rng=self.rng, opp_cards=r.hole_cards)
        except Exception as e:  # never fatal: the first decision just pays the cost
            warn(f"warm-up failed: {e!r}")

    # ---- equity
    def reconstruct(self, state: GameState):
        """The current hand rebuilt in bot.game (None if it can't be matched)."""
        h = state.hand
        try:
            rec = reconstruct(self.rules, h, self.rng, level=self._level(h))
            self._last_rec = (h.hand_id, rec)
            self._apply_trust()
            return rec
        except Exception as e:
            warn(f"reconstruction failed: {e!r}")
            return None

    def _level(self, h):
        if h.bb is not None:
            sb, bb, ante = h.sb, h.bb, h.ante or 0
            return (sb, bb, ante, getattr(self.rules, "straddle", 0))
        return None

    def equity(self, state: GameState, budget_s: float) -> float:
        h = state.hand
        assert h is not None
        if self._cache_hand != h.hand_id:
            self._cache, self._cache_hand = {}, h.hand_id
        # Shares change when we learn cards, or (with inference) when the opponent acts.
        n_opp = sum(1 for r in h.history if r.actor != ME) if self.inference.enabled else 0
        key = (len(h.card_log), h.hole, h.board, n_opp)
        if key not in self._cache:
            budget = budget_s * self.p["equity_budget_frac"]
            eq = None
            if (self.tables is not None and h.street == 0 and not h.board
                    and len(h.hole) == self.tables.classes.size and len(h.card_log) == 1):
                try:
                    eq = self.tables.start_share(h.hole)      # precomputed, no sampling
                except Exception:
                    eq = None
            if eq is None and self.p["use_sim"]:
                rec = self.reconstruct(state)
                if rec is not None:
                    try:
                        eq = expected_share(rec, self.rng, budget,
                                            max_samples=int(self.p["max_samples"]),
                                            worlds=int(self.p["rollout_worlds"]),
                                            inference=self.inference).share
                    except Exception as e:
                        warn(f"share estimate failed: {e!r}")
            if eq is None:
                runout = sum(self.rules.streets[h.street + 1:])
                eq = equity(h.hole, h.board, self.rules, time_budget_s=budget,
                            max_samples=int(self.p["max_samples"]), rng=self.rng,
                            opp_cards=len(h.hole), runout=runout).equity
            self._cache[key] = eq
        return self._cache[key]

    # ---- decision
    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        if legal.can_special:
            return self.special(state, legal, budget_s)
        h = state.hand
        if h is None or not h.hole:
            return safe_action(legal)
        eq = self.equity(state, budget_s)
        return self.choose(state, legal, eq, self.p)

    def special(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        """Generic simulation policy for a special step (default option on any failure)."""
        if self.p["use_sim"] and state.hand is not None:
            rec = self.reconstruct(state)
            if rec is not None:
                try:
                    return decide_special(rec, legal, self.rng,
                                          budget_s * self.p["special_budget_frac"],
                                          {"pimc_worlds": int(self.p["pimc_worlds"]),
                                           "_inference": self.inference})
                except Exception as e:
                    warn(f"special-step policy failed: {e!r}")
        return Action.special(legal.special.default())  # type: ignore[union-attr]

    def choose(self, state: GameState, legal: LegalActions, eq: float, p: dict) -> Action:
        """Equity -> action, using parameter dict `p` (Tier 2 passes adjusted copies)."""
        h = state.hand
        assert h is not None
        pot, to_call, street = h.pot, h.tocall, h.street
        my_raises = sum(1 for a in h.actions_on(street, ME) if a.kind == RAISE)

        if legal.can_raise and eq >= per_street(p["raise_equity"], street):
            if my_raises < p["max_own_raises"] or eq >= p["strong_equity"]:
                frac = p["strong_frac"] if eq >= p["strong_equity"] else p["value_frac"]
                r = pot_fraction_raise(frac, pot, to_call, h.my_bet, legal)
                if r is not None:
                    return r

        if to_call == 0:
            if (street > 0 and legal.can_raise and eq < p["bluff_max_equity"]
                    and self.pyrng.random() < p["bluff_freq"]):
                r = pot_fraction_raise(p["bluff_frac"], pot, 0, h.my_bet, legal)
                if r is not None:
                    return r
            return Action.check() if legal.check else safe_action(legal)

        pot_odds = to_call / (pot + to_call)
        need = pot_odds + p["call_margin"] + p["bet_pressure"] * to_call / max(pot, 1)
        if legal.call and eq >= need:
            return Action.call()
        return safe_action(legal)
