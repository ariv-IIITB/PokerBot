"""Brain interface. A brain sees only neutral objects: state, legal actions, time budget."""
from __future__ import annotations

from abc import ABC, abstractmethod

from bot.actions import Action, LegalActions
from bot.protocol import Message
from bot.state import GameState


class Brain(ABC):
    name = "base"

    @abstractmethod
    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        """Return an action. Should finish within `budget_s` seconds; the output is
        clamped to `legal` afterwards, and any exception falls back to Tier 0."""

    def observe(self, state: GameState, msg: Message) -> None:
        """Called after every engine message has been applied to `state` (optional hook,
        e.g. for opponent modelling). Exceptions here are logged and ignored."""
