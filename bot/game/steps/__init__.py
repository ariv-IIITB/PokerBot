"""Step-type registry: spec name -> plugin class.

Core steps are imported eagerly; the others only when a variant uses them (so the
submission package can leave unused plugins out). Add a plugin: write the module (see
_template.py), add one line to STEP_TYPES, and its parameters to variant/spec.STEP_PARAMS.
"""
from __future__ import annotations

import importlib

from bot.game.steps.base import CompileContext, Step
from bot.game.steps.basic import DealBoard, DealHole, PostBlinds
from bot.game.steps.betting import Betting
from bot.game.steps.hook import HookStep
from bot.game.steps.showdown import ShowdownStep

STEP_TYPES: dict[str, str] = {
    "post_blinds": "bot.game.steps.basic:PostBlinds",
    "deal_hole": "bot.game.steps.basic:DealHole",
    "deal_board": "bot.game.steps.basic:DealBoard",
    "betting": "bot.game.steps.betting:Betting",
    "hook": "bot.game.steps.hook:HookStep",
    "showdown": "bot.game.steps.showdown:ShowdownStep",
    "discard": "bot.game.steps.cards:Discard",
    "draw": "bot.game.steps.cards:Draw",
    "swap": "bot.game.steps.cards:Swap",
    "choose": "bot.game.steps.cards:Choose",
    "peek": "bot.game.steps.cards:Peek",
    "expose": "bot.game.steps.cards:Expose",
    "bounty": "bot.game.steps.side:Bounty",
    "auction": "bot.game.steps.side:Auction",
    "market": "bot.game.steps.side:Market",
    "redraw_board": "bot.game.steps.redraw:RedrawBoard",
}


def step_class(name: str) -> type[Step]:
    module, _, cls = STEP_TYPES[name].partition(":")
    return getattr(importlib.import_module(module), cls)


def step_module(name: str) -> str:
    return STEP_TYPES[name].partition(":")[0]


__all__ = ["STEP_TYPES", "CompileContext", "Step", "step_class", "step_module", "PostBlinds",
           "DealHole", "DealBoard", "Betting", "HookStep", "ShowdownStep"]
