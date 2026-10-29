"""The decision situation: what a brain knows about the decision in front of it, apart from
its strategy. `Perception` (one per match, owned by the brain) builds a `Situation` per
decision (`at(state)`; asking twice for the same decision returns the same object):

    rec               the hand rebuilt in bot.game (bot/sim/replay.py), at most once per
                      decision; None if it can't be matched. Each one goes to the Opponent.
    equity(budget)    our expected showdown share from here, by the fallback chain
                      precomputed table -> simulation (bot/sim/share.py) -> plain Monte Carlo;
                      cached per hand while our cards and the opponent's actions don't change
    special(legal, b) the simulation policy for a non-betting step (bot/sim/policies.py)
    locked()          the endgame lock: the match is won by check/folding everything left

Brains are policies over this (Tier 1, Tier 2, lab brains), so none has to inherit it.
Parameters (the brain's dict): equity_budget_frac, max_samples, use_sim, rollout_worlds,
special_budget_frac, pimc_worlds, discard_mode, smart_rollout_discard, use_tables,
table_range_weight, lock_enabled, lock_assume_alternating.
"""
from __future__ import annotations

from typing import Optional

from bot.actions import RAISE, Action, LegalActions
from bot.equity import equity
from bot.game.steps.cards import safe_action_for_hole
from bot.log import warn
from bot.sim.policies import decide_special
from bot.sim.replay import reconstruct
from bot.sim.share import expected_share
from bot.sim.tables import load_tables
from bot.state import ME, GameState

_UNSET = object()


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


class Situation:
    """One decision (see the module docstring)."""

    def __init__(self, perception: "Perception", state: GameState) -> None:
        self.pc, self.state, self.hand = perception, state, state.hand
        self._rec = _UNSET

    @property
    def rec(self):
        if self._rec is _UNSET:
            self._rec = self.pc._reconstruct(self.hand)
        return self._rec

    def equity(self, budget_s: float) -> float:
        return self.pc._equity(self, budget_s)

    def special(self, legal: LegalActions, budget_s: float) -> Action:
        """Simulation policy for a special step; without it (or on failure) the rules' own
        discard fallback, else the first option."""
        p = self.pc.p
        if p["use_sim"] and self.hand is not None and self.rec is not None:
            try:
                return decide_special(self.rec, legal, self.pc.rng,
                                      budget_s * p["special_budget_frac"],
                                      {"pimc_worlds": int(p["pimc_worlds"]),
                                       "discard_mode": str(p.get("discard_mode", "fast")),
                                       "_inference": self.pc.opponent.model})
            except Exception as e:
                warn(f"special-step policy failed: {e!r}")
        return safe_action_for_hole(legal, self.hand.hole if self.hand is not None else ())

    def locked(self) -> bool:
        """The endgame lock (off unless the brain's params set lock_enabled)."""
        p = self.pc.p
        if not p.get("lock_enabled", False):
            return False
        margin = lock_margin(self.state, bool(p.get("lock_assume_alternating", True)),
                             self.pc.rules)
        return margin is not None and margin > 0


class Perception:
    """Builds Situations for one brain: holds the rules, tables and per-hand equity cache."""

    def __init__(self, rules, params: dict, rng, opponent) -> None:
        self.p, self.rng, self.opponent = params, rng, opponent
        self._cache: dict = {}
        self._cache_hand: Optional[int] = None
        self._current: Optional[tuple] = None        # (decision key, Situation)
        self.set_rules(rules)

    def set_rules(self, rules) -> None:
        self.rules = rules
        self.tables = load_tables(rules) if self.p.get("use_tables", True) else None
        self._cache, self._cache_hand, self._current = {}, None, None

    def at(self, state: GameState) -> Situation:
        h = state.hand
        key = None if h is None else (h.hand_id, len(h.history), len(h.card_log))
        cur = self._current
        if key is None or cur is None or cur[0] != key or cur[1].state is not state:
            self._current = (key, Situation(self, state))
        return self._current[1]

    def warm_up(self) -> None:
        """Build evaluator tables and NumPy code paths before the first timed decision
        (the first equity call is ~60 ms, later ones well under 1 ms)."""
        try:
            r = self.rules
            equity(list(r.deck[:r.hole_cards]), (), r, max_samples=16, rng=self.rng,
                   opp_cards=r.hole_cards)
        except Exception as e:  # never fatal: the first decision just pays the cost
            warn(f"warm-up failed: {e!r}")

    # ---- internals of Situation
    def _reconstruct(self, h):
        if h is None:
            return None
        try:
            level = (h.sb, h.bb, h.ante or 0, getattr(self.rules, "straddle", 0)) \
                if h.bb is not None else None
            rec = reconstruct(self.rules, h, self.rng, level=level)
            rec.smart_discard = bool(self.p.get("smart_rollout_discard", False))
            self.opponent.saw(h.hand_id, rec)
            return rec
        except Exception as e:
            warn(f"reconstruction failed: {e!r}")
            return None

    def _equity(self, s: Situation, budget_s: float) -> float:
        h, p = s.hand, self.p
        assert h is not None
        if self._cache_hand != h.hand_id:
            self._cache, self._cache_hand = {}, h.hand_id
        # Shares change when we learn cards, or (with inference) when the opponent acts.
        n_opp = sum(1 for r in h.history if r.actor != ME) if self.opponent.model.enabled else 0
        key = (len(h.card_log), h.hole, h.board, n_opp)
        if key not in self._cache:
            budget = budget_s * p["equity_budget_frac"]
            eq = None
            if (self.tables is not None and h.street == 0 and not h.board
                    and len(h.hole) == self.tables.classes.size and len(h.card_log) == 1):
                try:
                    eq = self.tables.start_share(h.hole)      # precomputed, no sampling
                    w = float(p.get("table_range_weight", 0.0))
                    if (w > 0 and self.tables.eq_range is not None
                            and any(r.actor != ME and r.action.kind == RAISE for r in h.history)):
                        vs_range = float(self.tables.eq_range[self.tables.classes.class_of(h.hole)])
                        eq = (1 - w) * eq + w * vs_range      # a raiser's range is stronger than random
                except Exception:
                    eq = None
            if eq is None and p["use_sim"] and s.rec is not None:
                try:
                    eq = expected_share(s.rec, self.rng, budget,
                                        max_samples=int(p["max_samples"]),
                                        worlds=int(p["rollout_worlds"]),
                                        inference=self.opponent.model).share
                except Exception as e:
                    warn(f"share estimate failed: {e!r}")
            if eq is None:
                runout = sum(self.rules.streets[h.street + 1:])
                eq = equity(h.hole, h.board, self.rules, time_budget_s=budget,
                            max_samples=int(p["max_samples"]), rng=self.rng,
                            opp_cards=len(h.hole), runout=runout).equity
            self._cache[key] = eq
        return self._cache[key]
