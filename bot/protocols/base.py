"""The adapter interface (see bot/protocols/__init__.py).

A wire line need not map to one neutral message: the real protocol packs several into one
line (new_hand = HandStart + HoleCards) and spreads others over several. So:

  parse_line(line)     -> None, one Message, or a list of Messages (applied in order; at most
                          one is a request, and the bot replies once after the last)
  encode_message(msg)  -> "" (send nothing), one line, or a list of lines
"""
from __future__ import annotations

from typing import Optional, Union

from bot.actions import Action
from bot.protocol import Message


def as_messages(parsed: Union[None, Message, list, tuple]) -> list[Message]:
    """Normalize a parse_line result to a list of messages."""
    if parsed is None:
        return []
    return list(parsed) if isinstance(parsed, (list, tuple)) else [parsed]


def as_lines(encoded: Union[None, str, list, tuple]) -> list[str]:
    """Normalize an encode_message result to the non-empty lines to send."""
    if not encoded:
        return []
    return [encoded] if isinstance(encoded, str) else [x for x in encoded if x]


class Adapter:
    name = "base"
    # True if the wire format never tells us WHICH hidden card the opponent discarded (only
    # the card itself), so the neutral OppAction(special) carries a placeholder index.
    hides_opponent_choice = False
    # Seconds allowed per reply, from the engine's init message, when the format has one.
    per_response_s: Optional[float] = None

    # ---- bot side
    def parse_line(self, line: str) -> Union[None, Message, list]:
        raise NotImplementedError

    def encode_action(self, action: Action) -> str:
        raise NotImplementedError

    def recover(self, line: str) -> Optional[str]:
        """A reply to send when `line` could not be parsed but looks like a request (so the
        engine is waiting for us). None = say nothing."""
        return None

    # ---- engine side (lab)
    def encode_message(self, msg: Message) -> Union[str, list]:
        raise NotImplementedError

    def parse_action(self, line: str) -> Action:
        raise NotImplementedError
