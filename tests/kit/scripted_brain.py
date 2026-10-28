"""A brain that replies from a list, so a wire transcript can pin the exact replies."""
from __future__ import annotations

from typing import Optional, Sequence

from bot.actions import Action, LegalActions, safe_action
from bot.brains.base import Brain
from bot.state import GameState


class ScriptedBrain(Brain):
    """Answers the n-th request with script[n] (an Action); after the script, Tier 0.
    `seen` records the legal set of every request, for assertions."""
    name = "scripted"

    def __init__(self, script: Sequence[Action] = ()) -> None:
        self.script = list(script)
        self.calls = 0
        self.seen: list[LegalActions] = []

    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        self.seen.append(legal)
        i, self.calls = self.calls, self.calls + 1
        return self.script[i] if i < len(self.script) else safe_action(legal)


def make_brain(name: str, script: Optional[Sequence[Action]] = None) -> Brain:
    if name == "scripted":
        return ScriptedBrain(script or ())
    from lab.players import load_brain
    return load_brain(name)
