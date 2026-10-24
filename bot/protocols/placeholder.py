"""The placeholder format of bot/protocol.py, as an adapter (stateless)."""
from __future__ import annotations

from bot import protocol as P
from bot.protocols.base import Adapter


class PlaceholderAdapter(Adapter):
    name = "placeholder"

    def parse_line(self, line):
        return P.parse_line(line)

    def encode_action(self, action):
        return P.encode_action(action)

    def encode_message(self, msg):
        return P.encode_message(msg)

    def parse_action(self, line):
        return P.parse_action(line)
