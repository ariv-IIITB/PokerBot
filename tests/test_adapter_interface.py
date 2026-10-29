"""Adapters may pack several messages into one line, or none: the bot and the lab handle both."""
import io
import sys

from bot.actions import Action, LegalActions
from bot.brains.tier0 import Tier0Brain
from bot.main import Bot
from bot.protocol import ActRequest, HandStart, HoleCards, MatchInfo, OppAction
from bot.protocols import get_adapter
from bot.protocols.base import Adapter, as_lines, as_messages
from bot.cards import parse_cards
from lab.players import SubprocessPlayer


class Packing(Adapter):
    """Placeholder format where a line may hold several messages, joined by ' || '."""
    name = "packing"

    def __init__(self) -> None:
        self.inner = get_adapter("placeholder")

    def parse_line(self, line):
        parts = [self.inner.parse_line(p) for p in line.split(" || ")]
        return [m for m in parts if m is not None] if len(parts) > 1 else parts[0]

    def encode_action(self, action):
        return self.inner.encode_action(action)

    def encode_message(self, msg):
        if isinstance(msg, HoleCards):
            return ""                                   # merged into the next line instead
        if isinstance(msg, ActRequest):
            return [self.inner.encode_message(OppAction(Action.check())),
                    self.inner.encode_message(msg)]
        return self.inner.encode_message(msg)

    def parse_action(self, line):
        return self.inner.parse_action(line)


def test_normalizers() -> None:
    assert as_messages(None) == [] and as_messages(5) == [5] and as_messages((1, 2)) == [1, 2]
    assert as_lines(None) == [] and as_lines("") == [] and as_lines("a") == ["a"]
    assert as_lines(["a", "", "b"]) == ["a", "b"]


def test_bot_applies_every_message_of_a_line_and_replies_once() -> None:
    out = io.StringIO()
    bot = Bot(Tier0Brain(), out, adapter=Packing())
    ph = get_adapter("placeholder")
    lines = [ph.encode_message(MatchInfo()),
             " || ".join([ph.encode_message(HandStart(0, 0, 400, 400, 50.0)),
                          ph.encode_message(HoleCards(parse_cards("Ah,Kd"))),
                          ph.encode_message(OppAction(Action.raise_to(6))),
                          ph.encode_message(ActRequest(9, 4, 394, 394,
                                                       LegalActions(fold=True, call=True,
                                                                    raise_min=10, raise_max=394),
                                                       50.0, 2, 6))])]
    for line in lines:
        assert bot.handle_line(line)
    assert out.getvalue().splitlines() == ["F"]          # one reply, after the last message
    h = bot.state.hand
    assert h.hole == parse_cards("Ah,Kd") and h.history[0].action == Action.raise_to(6)


def test_a_line_with_no_known_message_gets_no_reply() -> None:
    out = io.StringIO()
    bot = Bot(Tier0Brain(), out, adapter=Packing())
    assert bot.handle_line("GARBAGE nothing") and out.getvalue() == ""


def test_subprocess_player_sends_each_line_of_a_message(monkeypatch) -> None:
    player = SubprocessPlayer([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        player.adapter = Packing()
        sent = []
        monkeypatch.setattr(player, "_send", sent.append)
        monkeypatch.setattr(player, "_read_line", lambda timeout: "K")
        player.notify(HoleCards(parse_cards("Ah,Kd")))             # "" -> nothing
        assert sent == []
        player.notify(OppAction(Action.call()))                    # one line
        assert len(sent) == 1
        req = ActRequest(3, 1, 399, 398, LegalActions(fold=True, call=True), 50.0, 1, 2)
        assert player.act(req) == Action.check()                   # two lines, then one reply
        assert len(sent) == 3 and sent[1].startswith("OPP") and sent[2].startswith("ACT")
    finally:
        player.close()
