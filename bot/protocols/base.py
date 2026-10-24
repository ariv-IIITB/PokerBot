"""The adapter interface (see bot/protocols/__init__.py)."""
from __future__ import annotations

from typing import Optional

from bot.actions import Action
from bot.protocol import Message


class Adapter:
    name = "base"

    # ---- bot side
    def parse_line(self, line: str) -> Optional[Message]:
        raise NotImplementedError

    def encode_action(self, action: Action) -> str:
        raise NotImplementedError

    # ---- engine side (lab)
    def encode_message(self, msg: Message) -> str:
        raise NotImplementedError

    def parse_action(self, line: str) -> Action:
        raise NotImplementedError
