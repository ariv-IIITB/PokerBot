"""Brain interface. A brain sees only neutral objects: state, legal actions, time budget."""
from __future__ import annotations

from abc import ABC, abstractmethod

from bot.actions import Action, LegalActions
from bot.protocol import Message
from bot.state import GameState


class Brain(ABC):
    name = "base"
    rules = None      # compiled bot.game Rules of the variant being played, if known
    # Endgame lock (bot/lock.py), applied by Bot.choose before the brain is asked.
    lock_enabled = False
    lock_assume_alternating = True    # blinds alternate each hand (False = assume BB always)

    def set_rules(self, rules) -> None:
        """Called by the lab before a match; the submitted bot uses its active variant."""
        self.rules = rules
        self.on_rules()

    def on_rules(self) -> None:
        """Hook: the variant changed (reload anything derived from the rules)."""

    @abstractmethod
    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        """Return an action. Should finish within `budget_s` seconds; the output is
        clamped to `legal` afterwards, and any exception falls back to Tier 0."""

    def observe(self, state: GameState, msg: Message) -> None:
        """Called after every engine message has been applied to `state` (optional hook,
        e.g. for opponent modelling). Exceptions here are logged and ignored."""
