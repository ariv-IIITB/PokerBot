"""Sparring brains with simple, recognisable styles (lab only, never submitted).

All take an optional config dict (e.g. {"seed": 3}) so the harness can build them.
Special steps (discards etc.) pick a random or first option; they only need to be legal.
"""
from __future__ import annotations

import random
from typing import Optional

from bot.actions import Action, LegalActions, pot_fraction_raise, safe_action
from bot.brains.base import Brain
from bot.cards import rank_of, suit_of
from bot.evaluator import PAIR, TWO_PAIR, category
from bot.state import GameState
from variant.evaluator_hook import make_evaluator
from variant.rules import DEFAULT_CONFIG


class _Sparring(Brain):
    def __init__(self, config: Optional[dict] = None) -> None:
        self.cfg = dict(config or {})
        self.rng = random.Random(self.cfg.get("seed", 0))

    def special(self, legal: LegalActions) -> Action:
        return Action.special(self.rng.choice(legal.special.choices))  # type: ignore[union-attr]

    def raise_frac(self, state: GameState, legal: LegalActions, frac: float) -> Optional[Action]:
        h = state.hand
        if h is None:
            return None
        return pot_fraction_raise(frac, h.pot, h.tocall, h.my_bet, legal)


class RandomLegal(_Sparring):
    """Uniform over legal action types; random raise size in the legal range."""
    name = "random_legal"

    def decide(self, state, legal, budget_s):
        if legal.can_special:
            return self.special(legal)
        opts = []
        if legal.fold:
            opts.append(Action.fold())
        if legal.check:
            opts.append(Action.check())
        if legal.call:
            opts.append(Action.call())
        if legal.can_raise:
            opts.append(Action.raise_to(self.rng.randint(legal.raise_min, legal.raise_max)))
        return self.rng.choice(opts) if opts else safe_action(legal)


class AllIn(_Sparring):
    """Shoves every decision."""
    name = "all_in"

    def decide(self, state, legal, budget_s):
        if legal.can_special:
            return self.special(legal)
        if legal.can_raise:
            return Action.raise_to(legal.raise_max)  # type: ignore[arg-type]
        return Action.call() if legal.call else safe_action(legal)


class CallingStation(_Sparring):
    """Never raises, never folds."""
    name = "calling_station"

    def decide(self, state, legal, budget_s):
        if legal.can_special:
            return self.special(legal)
        return Action.call() if legal.call else safe_action(legal)


class Maniac(_Sparring):
    """Raises ~70% of the time with big sizes; otherwise calls. Rarely folds."""
    name = "maniac"

    def decide(self, state, legal, budget_s):
        if legal.can_special:
            return self.special(legal)
        if legal.can_raise and self.rng.random() < self.cfg.get("raise_freq", 0.7):
            return self.raise_frac(state, legal, self.rng.choice([0.75, 1.0, 1.5]))  # type: ignore[return-value]
        if legal.call and self.rng.random() < 0.95:
            return Action.call()
        return safe_action(legal)


class Tight(_Sparring):
    """Plays only good starting hands; continues with a pair or better that uses its hole
    cards; raises premiums and strong made hands."""
    name = "tight"

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        self.ev = make_evaluator(DEFAULT_CONFIG)

    @staticmethod
    def preflop_score(hole) -> int:
        """0 = fold, 1 = playable, 2 = premium (for any number of hole cards)."""
        ranks = sorted((rank_of(c) for c in hole), reverse=True)
        paired = len(set(ranks)) < len(ranks)
        suited = len({suit_of(c) for c in hole}) < len(hole)
        if (paired and max(r for r in ranks if ranks.count(r) > 1) >= 9) or ranks[:2] == [12, 11]:
            return 2                                   # JJ+ or AK
        if paired and max(ranks) >= 5 or ranks[1] >= 8 or (ranks[0] == 12 and suited):
            return 1                                   # 77+, two cards T+, Ax suited
        return 0

    def made_strength(self, state: GameState) -> int:
        h = state.hand
        if h is None or len(h.hole) + len(h.board) < 5 or len(h.board) < 3:
            return 0
        try:
            mine = self.ev.evaluate(h.hole, h.board)
            board_only = self.ev.evaluate((), h.board) if len(h.board) >= 5 else -1
        except ValueError:
            return 0
        if mine <= board_only:
            return 0                                   # the board plays: nothing of ours
        cat = category(mine)
        return 2 if cat >= TWO_PAIR else (1 if cat >= PAIR else 0)

    def decide(self, state, legal, budget_s):
        if legal.can_special:
            return Action.special(legal.special.choices[0])  # type: ignore[union-attr]
        h = state.hand
        if h is None:
            return safe_action(legal)
        strength = self.preflop_score(h.hole) if h.street == 0 else self.made_strength(state)
        if strength == 2:
            r = self.raise_frac(state, legal, 0.75)
            if r is not None and h.tocall < h.my_stack // 2:
                return r
            return Action.call() if legal.call else safe_action(legal)
        if strength == 1:
            if legal.call and h.tocall <= max(4 * state.match.bb, h.pot // 2):
                return Action.call()
            return safe_action(legal)
        return safe_action(legal)
