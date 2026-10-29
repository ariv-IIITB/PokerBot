"""One decision, prepared once, under every simulation brain.

`Kit` (one per match, built by the brain from its parameters) holds the machinery: the rules,
the brain's random generator, the opponent (stats, inference, trust), the precomputed tables
and the per-hand equity cache. `kit.situation(state, legal, budget_s)` gives a `Situation`:

  rec        the hand rebuilt in bot.game (bot/sim/replay.py), at most once per decision and
             only when asked for; trust in the opponent model is applied when it is built.
             None if the hand can't be matched.
  equity()   expected showdown share, fallback chain: precomputed start-of-hand table ->
             simulated share from `rec` (inference-weighted) -> plain Monte Carlo equity
  special()  the generic simulation policy for a special step (PIMC discard, draw, bids, ...),
             the step's default option on any failure

Brains are policies over a Situation (bot/brains/tier1.py and subclasses). The endgame lock
and the emergency mode sit above all brains, in Bot.choose (bot/main.py).
"""
from __future__ import annotations

from typing import Optional

from bot.actions import Action, LegalActions
from bot.equity import equity
from bot.log import warn
from bot.sim.policies import decide_special
from bot.sim.replay import reconstruct
from bot.sim.share import expected_share
from bot.sim.tables import load_tables
from bot.state import ME, GameState

_UNBUILT = object()


class Kit:
    def __init__(self, params: dict, rules, rng, opponent) -> None:
        self.p, self.rng, self.opponent = params, rng, opponent
        self.rules = None
        self.tables = None
        self._cache: dict = {}
        self._cache_hand: Optional[int] = None
        self.set_rules(rules)

    def set_rules(self, rules) -> None:
        self.rules = rules
        self.tables = load_tables(rules) if self.p.get("use_tables", True) else None

    def situation(self, state: GameState, legal: LegalActions, budget_s: float) -> "Situation":
        return Situation(self, state, legal, budget_s)

    def warm_up(self) -> None:
        """Build evaluator tables and NumPy code paths before the first timed decision
        (the first equity call is ~60 ms, later ones well under 1 ms)."""
        try:
            r = self.rules
            hole = list(r.deck[:r.hole_cards])
            equity(hole, (), r, max_samples=16, rng=self.rng, opp_cards=r.hole_cards)
        except Exception as e:  # never fatal: the first decision just pays the cost
            warn(f"warm-up failed: {e!r}")


class Situation:
    def __init__(self, kit: Kit, state: GameState, legal: LegalActions, budget_s: float) -> None:
        self.kit, self.state, self.legal, self.budget_s = kit, state, legal, budget_s
        self.hand = state.hand
        self._rec = _UNBUILT

    @property
    def rec(self):
        """The current hand rebuilt in bot.game (None if it can't be matched)."""
        if self._rec is _UNBUILT:
            self._rec = self._reconstruct()
        return self._rec

    def _reconstruct(self):
        k, h = self.kit, self.hand
        try:
            rec = reconstruct(k.rules, h, k.rng, level=self._level())
            k.opponent.saw_hand(h.hand_id, rec)
            return rec
        except Exception as e:
            warn(f"reconstruction failed: {e!r}")
            return None

    def _level(self):
        h = self.hand
        if h.bb is not None:
            return (h.sb, h.bb, h.ante or 0, getattr(self.kit.rules, "straddle", 0))
        return None

    def equity(self) -> float:
        k, p, h = self.kit, self.kit.p, self.hand
        assert h is not None
        if k._cache_hand != h.hand_id:
            k._cache, k._cache_hand = {}, h.hand_id
        inference = k.opponent.inference
        # Shares change when we learn cards, or (with inference) when the opponent acts.
        n_opp = sum(1 for r in h.history if r.actor != ME) if inference.enabled else 0
        key = (len(h.card_log), h.hole, h.board, n_opp)
        if key not in k._cache:
            budget = self.budget_s * p["equity_budget_frac"]
            eq = None
            tables = k.tables
            if (tables is not None and h.street == 0 and not h.board
                    and len(h.hole) == tables.classes.size and len(h.card_log) == 1):
                try:
                    eq = tables.start_share(h.hole)           # precomputed, no sampling
                except Exception:
                    eq = None
            if eq is None and p["use_sim"]:
                rec = self.rec
                if rec is not None:
                    try:
                        eq = expected_share(rec, k.rng, budget,
                                            max_samples=int(p["max_samples"]),
                                            worlds=int(p["rollout_worlds"]),
                                            inference=inference).share
                    except Exception as e:
                        warn(f"share estimate failed: {e!r}")
            if eq is None:
                runout = sum(k.rules.streets[h.street + 1:])
                eq = equity(h.hole, h.board, k.rules, time_budget_s=budget,
                            max_samples=int(p["max_samples"]), rng=k.rng,
                            opp_cards=len(h.hole), runout=runout).equity
            k._cache[key] = eq
        return k._cache[key]

    def special(self) -> Action:
        """Generic simulation policy for a special step (default option on any failure)."""
        k, p, legal = self.kit, self.kit.p, self.legal
        if p["use_sim"] and self.hand is not None:
            rec = self.rec
            if rec is not None:
                try:
                    return decide_special(rec, legal, k.rng,
                                          self.budget_s * p["special_budget_frac"],
                                          {"pimc_worlds": int(p["pimc_worlds"]),
                                           "_inference": k.opponent.inference})
                except Exception as e:
                    warn(f"special-step policy failed: {e!r}")
        return Action.special(legal.special.default())  # type: ignore[union-attr]
