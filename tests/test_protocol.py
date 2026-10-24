import pytest

from bot.actions import Action, LegalActions, SpecialOption
from bot.cards import parse_cards
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, MatchEnd,
                          MatchInfo, OppAction, ProtocolError, Showdown, encode_action,
                          encode_message, format_legal, parse_action, parse_legal,
                          parse_line)

MESSAGES = [
    MatchInfo(hands=1000, timebank=55.5, sb=5, bb=10, stack=2000),
    HandStart(17, 0, 400, 400, 55.21),
    HandStart(18, 1, 390, 410, None),
    HoleCards(parse_cards("Ah,Kd")),
    HoleCards(parse_cards("Ah,Kd,2c,3c")),   # variants with more hole cards
    BoardUpdate(1, parse_cards("Ts,9h,2c")),
    BoardUpdate(0, ()),
    OppAction(Action.fold()), OppAction(Action.check()), OppAction(Action.call()),
    OppAction(Action.raise_to(6)), OppAction(Action.special("2")),
    ActRequest(9, 4, 398, 394, LegalActions(fold=True, call=True, raise_min=8,
                                             raise_max=400), 55.21),
    ActRequest(4, 0, 398, 398, LegalActions(check=True), None),
    ActRequest(4, 0, 398, 398, LegalActions(special=SpecialOption("discard", ("0", "1", "2")))),
    ActRequest(0, 0, 0, 0, LegalActions()),
    Showdown(parse_cards("Qs,Qd")),
    HandEnd(-6), HandEnd(0), HandEnd(400),
    MatchEnd(),
]


@pytest.mark.parametrize("msg", MESSAGES, ids=lambda m: type(m).__name__)
def test_message_round_trip(msg) -> None:
    line = encode_message(msg)
    assert "\n" not in line
    assert parse_line(line) == msg


def test_spec_example_lines() -> None:
    # The exact lines from the protocol spec parse as expected.
    act = parse_line("ACT pot=9 tocall=4 mystack=398 oppstack=394 legal=F,C,R:8-400 timeleft=55.21")
    assert isinstance(act, ActRequest)
    assert act.legal == LegalActions(fold=True, call=True, raise_min=8, raise_max=400)
    assert act.timeleft == pytest.approx(55.21)
    m = parse_line("MATCH hands=400 timebank=60.0 sb=1 bb=2 stack=400")
    assert m == MatchInfo(400, 60.0, 1, 2, 400)
    assert parse_line("OPP type=R amount=6") == OppAction(Action.raise_to(6))


@pytest.mark.parametrize("action", [Action.fold(), Action.check(), Action.call(),
                                    Action.raise_to(8), Action.special("1")])
def test_action_round_trip(action: Action) -> None:
    assert parse_action(encode_action(action)) == action


@pytest.mark.parametrize("bad", ["", "X", "R", "R abc", "R 1 2", "F 3", "S", "raise 8"])
def test_bad_replies(bad: str) -> None:
    with pytest.raises(ProtocolError):
        parse_action(bad)


def test_legal_round_trip() -> None:
    for text in ["F,C,R:8-400", "K,R:2-398", "S:discard:0|1|2", "F", "-", "F,K,C"]:
        assert format_legal(parse_legal(text)) == text


@pytest.mark.parametrize("line", ["", "   ", "HELLO world", "PING", "#comment", "\x00\x01"])
def test_unknown_lines_ignored(line: str) -> None:
    assert parse_line(line) is None


@pytest.mark.parametrize("line", [
    "HAND id=x seat=0 stack=400 oppstack=400",     # bad int
    "HAND seat=0",                                  # missing keys
    "HOLE cards=Zz,Ah",                             # bad card
    "HOLE cards=Ah,Ah",                             # duplicate card
    "BOARD street=1",                               # missing cards
    "ACT pot=9 tocall=4 mystack=1 oppstack=1 legal=Q",   # unknown legal token
    "ACT pot=9 tocall=4 mystack=1 oppstack=1 legal=R:8",  # bad range
    "OPP type=Z",
    "END delta=",
    "END garbage",
])
def test_malformed_known_lines_raise(line: str) -> None:
    with pytest.raises(ProtocolError):
        parse_line(line)


def test_unknown_keys_ignored() -> None:
    assert parse_line("END delta=5 extra=whatever") == HandEnd(5)
