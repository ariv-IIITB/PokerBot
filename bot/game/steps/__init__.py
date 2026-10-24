"""Step-type registry: name -> class. Variant specs refer to steps by these names."""
from __future__ import annotations

from bot.game.steps.base import Step
from bot.game.steps.basic import DealBoard, DealHole, PostBlinds
from bot.game.steps.betting import Betting
from bot.game.steps.cards import Choose, Discard, Draw, Expose, Peek, Swap
from bot.game.steps.hook import HookStep
from bot.game.steps.showdown import ShowdownStep

STEP_TYPES: dict[str, type[Step]] = {
    "post_blinds": PostBlinds,
    "deal_hole": DealHole,
    "deal_board": DealBoard,
    "betting": Betting,
    "hook": HookStep,
    "showdown": ShowdownStep,
    "discard": Discard,
    "draw": Draw,
    "swap": Swap,
    "choose": Choose,
    "peek": Peek,
    "expose": Expose,
}

__all__ = ["STEP_TYPES", "Step", "PostBlinds", "DealHole", "DealBoard", "Betting", "HookStep",
           "ShowdownStep", "Discard", "Draw", "Swap", "Choose", "Peek", "Expose"]
