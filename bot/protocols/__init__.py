"""Wire-format adapters. bot/protocol.py defines the neutral messages; each adapter here
maps one wire format onto them, for both sides:

    bot side     parse_line(line) -> None | Message | [Message, ...] (ProtocolError if malformed)
                 encode_action(action) -> reply line
    engine side  encode_message(msg) -> "" | line | [line, ...]   (the lab's SubprocessPlayer)
                 parse_action(line) -> Action

Adapters may keep state (e.g. the last ACT, to convert "raise BY" replies). Select one
with `python -m bot.main --protocol NAME` or $POKERBOT_PROTOCOL. On reveal day the real
engine's format becomes a new module here (see docs/PROTOCOL_ADAPTER_GUIDE.md).
"""
from __future__ import annotations

import os

from bot.protocols.base import Adapter
from bot.protocols.placeholder import PlaceholderAdapter

ADAPTERS = {
    "placeholder": "bot.protocols.placeholder:PlaceholderAdapter",
    "json": "bot.protocols.jsonl:JsonLinesAdapter",
    "terse": "bot.protocols.terse:TerseAdapter",
    "pokerbots": "bot.protocols.pokerbots:PokerbotsAdapter",
}
DEFAULT = "pokerbots"          # the official wire format; the others are mock formats for tests


def get_adapter(name: str | None = None) -> Adapter:
    """A fresh adapter instance (name, else $POKERBOT_PROTOCOL, else the default)."""
    import importlib
    name = name or os.environ.get("POKERBOT_PROTOCOL") or DEFAULT
    module, _, cls = ADAPTERS[name].partition(":")
    return getattr(importlib.import_module(module), cls)()


__all__ = ["ADAPTERS", "DEFAULT", "Adapter", "PlaceholderAdapter", "get_adapter"]
