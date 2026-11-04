"""Adversary bot (lab only): an over-folder that changes style, to test tier4p's bail-out.

For the first SWITCH_AT hands it folds to any postflop bet unless it has a pair or better that uses its
hole cards (the over-folder family); it calls preflop and never raises. From hand SWITCH_AT on it
calls everything down (a calling station). Config: {"seed": n, "switch_at": 100, "min_hand": 1}.
`min_hand` is the made-hand strength it continues with before the switch: 1 = pair or better (the
default; about 45 % folds to a bet, which X1 rates as not an over-folder), 2 = two pair or better
(`adversary_strict`: folds ~80 %, a clear over-folder, so tier4p's bail-out can be exercised).
"""
from __future__ import annotations

from typing import Optional

from bot.actions import Action, LegalActions, safe_action
from bot.state import GameState
from lab.sparring.bots import Tight, _Sparring

SWITCH_AT = 100


class Adversary(_Sparring):
    name = "adversary"

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        self.switch_at = int(self.cfg.get("switch_at", SWITCH_AT))
        self.ev = None
        self.min_hand = int(self.cfg.get("min_hand", 1))

    def on_rules(self) -> None:
        self.ev = self.rules.evaluator

    def _has_pair(self, state: GameState) -> bool:
        h = state.hand
        if self.ev is None:
            self.ev = self.rules.evaluator
        if h is None or len(h.board) < 3:
            return False
        helper = Tight.__new__(Tight)
        helper.ev = self.ev
        return Tight.made_strength(helper, state) >= self.min_hand

    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        if legal.can_special:
            return self.special(legal)
        h = state.hand
        if (h is not None and state.hands_played < self.switch_at and h.street >= 1 and h.tocall > 0
                and legal.fold and not self._has_pair(state)):
            return Action.fold()
        return Action.call() if legal.call else safe_action(legal)


class AdversaryStrict(Adversary):
    """Continues only with two pair or better before the switch: a clear over-folder."""
    name = "adversary_strict"

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__({"min_hand": 2, **(config or {})})
