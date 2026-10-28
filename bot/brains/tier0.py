"""Tier 0: the always-safe fallback. Check when free, otherwise fold; a discard follows the
rules' fallback (the lowest-ranked hole card), other special steps take the first choice."""
from __future__ import annotations

from bot.actions import Action, LegalActions
from bot.brains.base import Brain
from bot.game.steps.cards import safe_action_for_hole
from bot.state import GameState


class Tier0Brain(Brain):
    name = "tier0"

    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        hand = state.hand
        return safe_action_for_hole(legal, hand.hole if hand is not None else ())
