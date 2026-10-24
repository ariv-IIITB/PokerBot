"""Tier 1: Monte Carlo equity vs pot odds, with raise thresholds and randomized bluffs.

Per decision:
  1. equity = MC equity vs a random hand (time-budgeted, cached per hand+board)
  2. equity >= raise threshold for this street -> value raise (pot-fraction sizing)
  3. nobody has bet, weak hand, not preflop -> bluff with probability bluff_freq
  4. facing a bet: call if equity >= pot odds + margin (+ pressure for big bets)
  5. otherwise check if free, else fold
Special steps (discards etc.) take the first option; variant-aware policies come later.
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
from bot.protocol import MatchInfo, Message
from bot.state import ME, GameState
from variant.rules import DEFAULT_CONFIG, GameConfig

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
}


class Tier1Brain(Brain):
    name = "tier1"
    param_file = "tier1"

    def __init__(self, config: Optional[dict] = None, game: GameConfig = DEFAULT_CONFIG,
                 config_dir=None) -> None:
        self.p = load_params(self.param_file, self.defaults(), config, config_dir)
        self.game = game
        self.rng = np.random.default_rng(int(self.p["seed"]))
        self.pyrng = random.Random(int(self.p["seed"]))
        self._cache: dict = {}
        self._cache_hand: Optional[int] = None

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return dict(DEFAULTS)

    # ---- warm-up
    def observe(self, state: GameState, msg: Message) -> None:
        if isinstance(msg, MatchInfo):
            self.warm_up()

    def warm_up(self) -> None:
        """Build evaluator tables and NumPy code paths before the first timed decision
        (the first equity call is ~60 ms, later ones well under 1 ms)."""
        try:
            hole = list(range(self.game.hole_cards))
            equity(hole, (), self.game, max_samples=16, rng=self.rng)
        except Exception as e:  # never fatal: the first decision just pays the cost
            warn(f"warm-up failed: {e!r}")

    # ---- equity
    def equity(self, state: GameState, budget_s: float) -> float:
        h = state.hand
        assert h is not None
        if self._cache_hand != h.hand_id:
            self._cache, self._cache_hand = {}, h.hand_id
        key = (h.hole, h.board)
        if key not in self._cache:
            runout = sum(self.game.streets[h.street + 1:])
            r = equity(h.hole, h.board, self.game, time_budget_s=budget_s * self.p["equity_budget_frac"],
                       max_samples=int(self.p["max_samples"]), rng=self.rng,
                       opp_cards=len(h.hole), runout=runout)
            self._cache[key] = r.equity
        return self._cache[key]

    # ---- decision
    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        if legal.can_special:
            return Action.special(legal.special.choices[0])  # type: ignore[union-attr]
        h = state.hand
        if h is None or not h.hole:
            return safe_action(legal)
        eq = self.equity(state, budget_s)
        return self.choose(state, legal, eq, self.p)

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
