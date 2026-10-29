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
from bot.game.rules_spec import active_rules, to_rules
from bot.opponent import Opponent
from bot.protocol import MatchInfo, Message
from bot.situation import Kit, Situation
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
    "inference": True,             # weight opponent hands by their visible choices
    "inference_beta": 6.0,
    "inference_gamma": 3.0,
    "inference_trust": True,       # scale inference by how well it predicted past showdowns
    "use_tables": True,            # precomputed start-of-hand shares, if valid data exists
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
        self.opponent = Opponent(self.rng, self.p.get("priors"), float(self.p.get("prior_k", 15.0)),
                                 inference=bool(self.p["inference"]),
                                 beta=float(self.p["inference_beta"]),
                                 gamma=float(self.p["inference_gamma"]),
                                 use_trust=bool(self.p["inference_trust"]))
        self.kit = Kit(self.p, self.rules, self.rng, self.opponent)

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return dict(DEFAULTS)

    def on_rules(self) -> None:
        self.kit.set_rules(self.rules)

    def observe(self, state: GameState, msg: Message) -> None:
        if isinstance(msg, MatchInfo):
            self.kit.warm_up()
        self.opponent.observe(state, msg)

    # ---- decision
    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        return self.act(self.kit.situation(state, legal, budget_s))

    def act(self, sit: Situation) -> Action:
        """The policy: a special step goes to the simulation policy, a bet to `choose`."""
        if sit.legal.can_special:
            return sit.special()
        h = sit.hand
        if h is None or not h.hole:
            return safe_action(sit.legal)
        return self.choose(sit.state, sit.legal, sit.equity(), self.params())

    def params(self) -> dict[str, Any]:
        """The parameters `choose` uses (Tier 2 shifts them by the opponent model)."""
        return self.p

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
