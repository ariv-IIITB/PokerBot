"""Shared test helpers: scripted matches as neutral messages, encoded with any adapter.

The wire format under test is $POKERBOT_PROTOCOL (default: placeholder), so the whole suite
can be rerun against another adapter:  POKERBOT_PROTOCOL=json .venv/bin/python -m pytest
"""
from __future__ import annotations

import os
from typing import Optional

from bot.actions import Action, LegalActions, SpecialOption
from bot.cards import parse_cards
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, MatchEnd,
                          MatchInfo, Message, OppAction, Showdown)
from bot.protocols import DEFAULT, get_adapter


def protocol_name() -> str:
    return os.environ.get("POKERBOT_PROTOCOL") or DEFAULT


def scripted_hand_messages(hand_id: int, timeleft: float = 50.0) -> list[Message]:
    """One hand with 4 decisions for us, including a special (discard) step."""
    return [
        HandStart(hand_id, hand_id % 2, 400, 400, timeleft),
        HoleCards(parse_cards("Ah,Kd")),
        ActRequest(3, 1, 399, 398, LegalActions(fold=True, call=True, raise_min=4,
                                                 raise_max=400), timeleft, 1, 2),
        OppAction(Action.check()),
        BoardUpdate(1, parse_cards("Ts,9h,2c")),
        ActRequest(4, 0, 398, 398, LegalActions(check=True, raise_min=2, raise_max=398),
                   timeleft, 0, 0),
        ActRequest(4, 0, 398, 398,
                   LegalActions(special=SpecialOption("discard", ("0", "1", "2"))), timeleft, 0, 0),
        OppAction(Action.raise_to(10)),
        ActRequest(14, 10, 398, 388, LegalActions(fold=True, call=True, raise_min=20,
                                                   raise_max=398), timeleft, 0, 10),
        Showdown(parse_cards("Qs,Qd")),
        HandEnd(-2),
    ]


def scripted_messages(hands: int = 3, timebank: float = 60.0,
                      timeleft: float = 50.0) -> list[Message]:
    msgs: list[Message] = [MatchInfo(hands=hands, timebank=timebank)]
    for i in range(hands):
        msgs += scripted_hand_messages(i, timeleft)
    msgs.append(MatchEnd())
    return msgs


def encode(msgs: list[Message], adapter: Optional[str] = None) -> list[str]:
    a = get_adapter(adapter or protocol_name())
    return [a.encode_message(m) for m in msgs]


def scripted_match(hands: int = 3, timebank: float = 60.0, adapter: Optional[str] = None,
                   timeleft: float = 50.0) -> list[str]:
    return encode(scripted_messages(hands, timebank, timeleft), adapter)


def decode_replies(msgs: list[Message], replies: list[str],
                   adapter: Optional[str] = None) -> list[Action]:
    """Engine-side decoding of the bot's replies, one per ActRequest (adapters may need
    the ACT each reply answers, e.g. for "raise BY")."""
    a = get_adapter(adapter or protocol_name())
    out, it = [], iter(replies)
    for m in msgs:
        a.encode_message(m)
        if isinstance(m, ActRequest):
            out.append(a.parse_action(next(it)))
    return out


# Lines each adapter must reject as malformed (known message type, bad contents).
MALFORMED = {
    "placeholder": ["ACT pot=oops", "HOLE cards=ZZ", "MATCH hands=x", "END delta=abc"],
    "json": ['{"type": "act", "pot": 1}', '{"type": "hole", "cards": ["Zz"]}',
             '{"type": "end"', '[1, 2]'],
    "terse": ["A 1 2", "C ZZ", "H 1 Q 400 400", "E abc"],
}
