"""Tier 0: the always-safe fallback. Check when free, otherwise fold; first special choice."""
from __future__ import annotations

from bot.actions import Action, LegalActions, safe_action
from bot.brains.base import Brain
from bot.state import GameState


class Tier0Brain(Brain):
    name = "tier0"

    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        return safe_action(legal)
