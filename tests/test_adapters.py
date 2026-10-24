"""Adapter conformance suite: every wire-format adapter in bot/protocols must pass this.

To add an adapter: register it in bot/protocols/ADAPTERS, add malformed examples to
tests/helpers.MALFORMED, and run this file (then the whole suite with
POKERBOT_PROTOCOL=<name>).
"""
import random
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import MALFORMED

from bot.actions import Action, LegalActions, SpecialOption
from bot.cards import parse_cards as P
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, Info,
                          MatchEnd, MatchInfo, OppAction, ProtocolError, Showdown)
from bot.protocols import ADAPTERS, get_adapter
from lab.engine import play_match
from lab.players import PlayerSpec, SubprocessPlayer
from variant.spec import load_catalog

ROOT = Path(__file__).resolve().parent.parent
NAMES = sorted(ADAPTERS)

# Every message shape the engine produces (ACTs always carry both street bets).
LEGALS = [
    LegalActions(fold=True, call=True, raise_min=8, raise_max=400),
    LegalActions(check=True, raise_min=2, raise_max=398),
    LegalActions(fold=True, call=True),
    LegalActions(),
    LegalActions(special=SpecialOption("discard", ("0", "1", "2"))),
    LegalActions(special=SpecialOption("draw", ("none", "0", "1", "0+1"))),
    LegalActions(special=SpecialOption("swap", ("none", "h0b1", "h1b2"))),
    LegalActions(special=SpecialOption("peek", ("no", "yes"))),
    LegalActions(special=SpecialOption("bid", (), 0, 57)),
    LegalActions(fold=True, call=True, raise_min=4, raise_max=400, raise_sizes=(4, 6, 400)),
    LegalActions(fold=True, call=True, raise_min=5, raise_max=403, raise_step=5),
]
MESSAGES = (
    [MatchInfo(), MatchInfo(1000, 55.5, 5, 10, 2000),
     HandStart(17, 0, 400, 400, 55.21), HandStart(18, 1, 390, 410, None),
     HandStart(120, 1, 400, 400, 50.0, 2, 4, 1),
     HoleCards(P("Ah,Kd")), HoleCards(P("Ah,Kd,2c,3c,4h,5s")), HoleCards(()),
     BoardUpdate(1, P("Ts,9h,2c")), BoardUpdate(0, ()), BoardUpdate(2, P("Ts,9h,2c,4d"), 1),
     OppAction(Action.fold()), OppAction(Action.check()), OppAction(Action.call()),
     OppAction(Action.raise_to(6)), OppAction(Action.special("0+2")),
     OppAction(Action.special("hidden")), OppAction(Action.special("17")),
     Showdown(P("Qs,Qd")), Info("expose", "opp", P("Ah")), Info("bounty", "none", (), 12),
     Info("run", "none", P("2c,3d,4h,5s,6c"), 1), Info("offer", "me", P("2c,3d,4h")),
     HandEnd(-6), HandEnd(0), MatchEnd()]
    + [ActRequest(9, 4, 398, 394, L, 55.21, 2, 6) for L in LEGALS]
    + [ActRequest(0, 0, 0, 0, LegalActions(), None, 0, 0)]
)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("i", range(len(MESSAGES)))
def test_message_round_trip(name, i) -> None:
    msg = MESSAGES[i]
    engine, bot = get_adapter(name), get_adapter(name)
    line = engine.encode_message(msg)
    assert "\n" not in line
    assert bot.parse_line(line) == msg


def candidate_actions(L: LegalActions) -> list[Action]:
    out = [a for a, ok in [(Action.fold(), L.fold), (Action.check(), L.check),
                           (Action.call(), L.call)] if ok]
    if L.can_raise:
        amounts = list(L.raise_sizes) if L.raise_sizes else [L.raise_min, L.raise_max,
                                                            (L.raise_min + L.raise_max) // 2]
        out += [Action.raise_to(a) for a in amounts]
    if L.can_special:
        sp = L.special
        out += ([Action.special(str(v)) for v in (sp.lo, sp.hi)] if sp.is_range
                else [Action.special(c) for c in sp.choices])
    return out


@pytest.mark.parametrize("name", NAMES)
def test_action_round_trip_in_context(name) -> None:
    """Replies are decoded in the context of the ACT they answer (e.g. raise BY)."""
    engine, bot = get_adapter(name), get_adapter(name)
    for L in LEGALS:
        for bets in [(0, 0), (2, 6), (10, 4)]:
            req = ActRequest(20, max(0, bets[1] - bets[0]), 380, 376, L, 30.0, *bets)
            assert bot.parse_line(engine.encode_message(req)) == req
            for a in candidate_actions(L):
                assert engine.parse_action(bot.encode_action(a)) == a, (L, bets, a)


@pytest.mark.parametrize("name", NAMES)
def test_garbage_never_crashes(name) -> None:
    a = get_adapter(name)
    rng = random.Random(0)
    alphabet = "ACHMOTXZIE {}[]\":,=-~|/0123456789abcdefKQJTshdcrxyz\x00\xff"
    for _ in range(3000):
        line = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        try:
            a.parse_line(line)
        except ProtocolError:
            pass
        try:
            a.parse_action(line)
        except ProtocolError:
            pass


@pytest.mark.parametrize("name", NAMES)
def test_malformed_known_lines_raise(name) -> None:
    a = get_adapter(name)
    for line in MALFORMED[name]:
        with pytest.raises(ProtocolError):
            a.parse_line(line)


@pytest.mark.parametrize("name", NAMES)
def test_bot_process_eof_and_empty_input(name) -> None:
    env = {"POKERBOT_PROTOCOL": name}
    import os
    env = dict(os.environ, **env)
    for data in (b"", get_adapter(name).encode_message(MatchInfo()).encode() + b"\n"):
        proc = subprocess.run([sys.executable, "-m", "bot.main"], input=data, cwd=ROOT,
                              capture_output=True, timeout=30, env=env)
        assert proc.returncode == 0 and proc.stdout == b""


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("variant", ["holdem_nl", "mit2026_discard", "auction_card",
                                     "three_boards", "escalating_blinds", "side_market"])
def test_full_match_over_the_wire(name, variant) -> None:
    bot = SubprocessPlayer([sys.executable, "-m", "bot.main", "--brain", "tier2"], protocol=name)
    m = play_match([bot, PlayerSpec.brain("maniac").build()], load_catalog()[variant],
                   seed=3, hands=10, audit=True)
    assert m.forfeit is None and m.errors == [0, 0], m.forfeit_reason
