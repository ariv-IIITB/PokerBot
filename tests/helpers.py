"""Shared test helpers: a scripted placeholder-protocol match (engine side)."""
from __future__ import annotations

from bot.actions import Action, LegalActions, SpecialOption
from bot.cards import parse_cards
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, MatchEnd,
                          MatchInfo, OppAction, Showdown, encode_message)


def scripted_hand(hand_id: int, timeleft: float = 50.0) -> list[str]:
    """One hand with 4 decisions for us, including a special (discard) step."""
    msgs = [
        HandStart(hand_id, hand_id % 2, 400, 400, timeleft),
        HoleCards(parse_cards("Ah,Kd")),
        ActRequest(3, 1, 399, 398, LegalActions(fold=True, call=True, raise_min=4,
                                                 raise_max=400), timeleft),
        OppAction(Action.check()),
        BoardUpdate(1, parse_cards("Ts,9h,2c")),
        ActRequest(4, 0, 398, 398, LegalActions(check=True, raise_min=2, raise_max=398),
                   timeleft),
        ActRequest(4, 0, 398, 398,
                   LegalActions(special=SpecialOption("discard", ("0", "1", "2"))), timeleft),
        OppAction(Action.raise_to(10)),
        ActRequest(14, 10, 398, 388, LegalActions(fold=True, call=True, raise_min=20,
                                                   raise_max=398), timeleft),
        Showdown(parse_cards("Qs,Qd")),
        HandEnd(-2),
    ]
    return [encode_message(m) for m in msgs]


def scripted_match(hands: int = 3, timebank: float = 60.0) -> list[str]:
    lines = [encode_message(MatchInfo(hands=hands, timebank=timebank))]
    for i in range(hands):
        lines += scripted_hand(i)
    lines.append(encode_message(MatchEnd()))
    return lines
