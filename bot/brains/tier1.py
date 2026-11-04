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
from bot.opponent import Opponent
from bot.protocol import MatchInfo, Message
from bot.game.rules_spec import active_rules, to_rules
from bot.situation import Perception, Situation
from bot.state import ME, GameState

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
    "discard_mode": "fast",        # one-card discards: fast | pimc | lowest | highest2 (bot/sim/policies.py)
    "smart_rollout_discard": False,# (E1: +3 vs stations, -1.3 vs tier1: off until retuned) rollouts keep the best two cards instead of discarding at random
    "inference": True,             # weight opponent hands by their visible choices
    "inference_beta": 6.0,
    "inference_gamma": 3.0,
    "discard_mix": 0.0,            # DC: weight of the straight-draw rule in the opponent's discard model (0 = off)
    "discard_eps": 0.25,           # ... share of random discards in it
    "discard_learn": False,        # DC: learn the opponent's keep rule online from showdown discards
    "discard_max_samples": 4000,   # worlds sampled per fast discard at most (the budget stops it earlier)
    "inference_trust": True,       # scale inference by how well it predicted past showdowns
    "use_tables": True,            # precomputed start-of-hand shares, if valid data exists
    "table_range_weight": 0.0,     # facing a preflop raise: blend in the share vs a top-range opponent
}


class Tier1Brain(Brain):
    name = "tier1"
    param_file = "tier1"

    def __init__(self, config: Optional[dict] = None, game=None) -> None:
        self.p = load_params(self.param_file, self.defaults(), config)
        # `game`: VariantSpec or Rules; default = the bot's active variant.
        self.rules = to_rules(game) if game is not None else active_rules()
        self.rng = np.random.default_rng(int(self.p["seed"]))
        self.pyrng = random.Random(int(self.p["seed"]))
        self.opponent = Opponent({"enabled": bool(self.p["inference"]),
                                  "beta": float(self.p["inference_beta"]),
                                  "gamma": float(self.p["inference_gamma"]),
                                  "ref_hands": 120, "min_ess": 0.08,
                                  "discard_mix": float(self.p["discard_mix"]),
                                  "discard_eps": float(self.p["discard_eps"]),
                                  "discard_max_samples": int(self.p["discard_max_samples"]),
                                  "discard_learn": bool(self.p["discard_learn"])},
                                 use_trust=bool(self.p["inference_trust"]),
                                 priors=self.p.get("priors"), k=float(self.p.get("prior_k", 15.0)))
        self.perception = Perception(self.rules, self.p, self.rng, self.opponent)

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return dict(DEFAULTS)

    def on_rules(self) -> None:
        self.perception.set_rules(self.rules)

    def observe(self, state: GameState, msg: Message) -> None:
        if isinstance(msg, MatchInfo):
            self.perception.warm_up()
        self.opponent.observe(state, msg, self.rng, self.rules)

    def situation(self, state: GameState) -> Situation:
        """Everything about this decision that is not strategy (bot/situation.py)."""
        return self.perception.at(state)

    # ---- decision
    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        return self.play(self.situation(state), legal, budget_s, self.p)

    def play(self, s: Situation, legal: LegalActions, budget_s: float, p: dict) -> Action:
        """Special steps go to the simulation policy; bets to `choose` with params `p`."""
        if legal.can_special:
            return s.special(legal, budget_s)
        if s.hand is None or not s.hand.hole:
            return safe_action(legal)
        return self.choose(s.state, legal, s.equity(budget_s), p)

    def sized_raise(self, frac: float, kind: str, eq: float, state: GameState,
                    legal: LegalActions, p: dict) -> Optional[Action]:
        """The raise for a decision already taken: `frac` x pot (kind: "value" or "bluff").
        Tier 2 overrides this to size by expected value."""
        h = state.hand
        assert h is not None
        return pot_fraction_raise(frac, h.pot, h.tocall if kind == "value" else 0, h.my_bet, legal)

    def choose(self, state: GameState, legal: LegalActions, eq: float, p: dict) -> Action:
        """Equity -> action, using parameter dict `p` (Tier 2 passes adjusted copies)."""
        h = state.hand
        assert h is not None
        pot, to_call, street = h.pot, h.tocall, h.street
        my_raises = sum(1 for a in h.actions_on(street, ME) if a.kind == RAISE)

        if legal.can_raise and eq >= per_street(p["raise_equity"], street):
            if my_raises < p["max_own_raises"] or eq >= p["strong_equity"]:
                strong = eq >= p["strong_equity"]
                r = self.sized_raise(p["strong_frac"] if strong else p["value_frac"], "value",
                                     eq, state, legal, p)
                if r is not None:
                    return r

        if to_call == 0:
            if (street > 0 and legal.can_raise and eq < p["bluff_max_equity"]
                    and self.pyrng.random() < p["bluff_freq"]):
                r = self.sized_raise(p["bluff_frac"], "bluff", eq, state, legal, p)
                if r is not None:
                    return r
            return Action.check() if legal.check else safe_action(legal)

        pot_odds = to_call / (pot + to_call)
        need = pot_odds + p["call_margin"] + p["bet_pressure"] * to_call / max(pot, 1)
        if legal.call and eq >= need:
            return Action.call()
        return safe_action(legal)
