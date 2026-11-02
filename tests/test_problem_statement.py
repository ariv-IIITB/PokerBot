"""The Problem Statement's worked examples (docs/rules/problem_statement.pdf, section 8) as tests.

Engine rules go through the scenario kit; the bot side runs the PS lines through the real
`pokerbots` adapter in-process and through `python bot.py` as a subprocess. Numbers are the PS's."""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from kit.scenario import Scenario, rigged_deck, run_scenario
from kit.scripted_brain import make_brain
from kit.transcript import read_transcript, replay_transcript

from bot.actions import Action
from bot.cards import format_card, parse_cards
from bot.evaluator import GenericEvaluator
from bot.main import Bot
from bot.game.rules_spec import to_rules
from bot.protocol import Info
from bot.protocols import get_adapter
from lab.engine import Hand, Seat
from variant.spec import load_catalog

SPEC = "discard_holdem"
FIX = Path(__file__).parent / "fixtures" / "protocol"
ROOT = Path(__file__).resolve().parent.parent
EV = GenericEvaluator()


def sc(holes, board, steps, expect=None, unfinished=False) -> Scenario:
    return Scenario(SPEC, holes, board, steps, expect or {}, unfinished=unfinished)


# --------------------------------------------------------------------------- 8.1

EX1_HOLES = {"SB": ["Qh", "Jh", "4c"], "BB": ["9s", "9d", "Kc"]}
EX1_BOARD = ["Th", "9h", "2c", "3s", "5h"]


def ex1_steps():
    return [("SB", "raise 6", {"legal": {"fold", "call", "raise"}, "min": 4, "max": 200, "pot": 3}),
            ("BB", "call", {"pot": 8}),
            ("BB", "check", {"street": "flop", "pot": 12}),
            ("SB", "raise 8", {"min": 2, "pot": 12}),
            ("BB", "raise 24", {"min": 16, "pot": 20}),                 # 8 + max(8, 2)
            ("SB", "call", {"pot": 44, "tocall": 16}),
            ("SB", "discard 4c", {"pot": 60, "stack": 170, "legal": {"discard"}}),   # 170 behind
            ("BB", "discard Kc", {"stack": 170}),
            ("BB", "raise 40", {"street": "turn", "pot": 60}),
            ("SB", "call", {"pot": 100}),
            ("BB", "check", {"street": "river", "pot": 140, "stack": 130}),         # 130 behind
            ("SB", "raise 70", {"pot": 140}),
            ("BB", "call", {"pot": 210})]


def test_ex_8_1_full_hand_to_showdown() -> None:
    st = run_scenario(sc(EX1_HOLES, EX1_BOARD, ex1_steps(),
                         {"deltas": {"SB": 140, "BB": -140}, "showdown": True, "pot": 280,
                          "muck": ["4c", "Kc"], "hole": {"SB": ["Qh", "Jh"], "BB": ["9s", "9d"]}}))
    assert st.deltas == [140, -140]


def test_ex_8_1_showdown_hands() -> None:
    a = EV.evaluate(parse_cards("Qh,Jh"), parse_cards(",".join(EX1_BOARD)))
    b = EV.evaluate(parse_cards("9s,9d"), parse_cards(",".join(EX1_BOARD)))
    assert a > b                                                   # flush beats three nines


def test_ex_8_1_the_duplicate_swaps_the_seats() -> None:
    swapped = {"SB": EX1_HOLES["BB"], "BB": EX1_HOLES["SB"]}
    # The same betting with the seats swapped: now the 9s player (on the button) loses 140.
    steps = [("SB", "raise 6", {}), ("BB", "call", {}), ("BB", "check", {}), ("SB", "raise 8", {}),
             ("BB", "raise 24", {}), ("SB", "call", {}), ("SB", "discard Kc", {}),
             ("BB", "discard 4c", {}), ("BB", "raise 40", {}), ("SB", "call", {}),
             ("BB", "check", {}), ("SB", "raise 70", {}), ("BB", "call", {})]
    run_scenario(sc(swapped, EX1_BOARD, steps, {"deltas": {"SB": -140, "BB": 140}}))


# --------------------------------------------------------------------------- 8.2

def test_ex_8_2_min_raises_and_the_raise_cap() -> None:
    run_scenario(sc(EX1_HOLES, EX1_BOARD,
                    [("SB", "raise 6", {"min": 4}),
                     ("BB", "raise 18", {"min": 10}),
                     ("SB", "raise 50", {"min": 30}),
                     ("BB", "call", {"legal": {"fold", "call"}}),        # cap reached
                     ("BB", "check", {"street": "flop", "pot": 100, "stack": 150})],
                    unfinished=True))


# --------------------------------------------------------------------------- 8.3

def test_ex_8_3_preflop_all_in_still_discards() -> None:
    holes = {"SB": ["As", "Ad", "5c"], "BB": ["Kh", "Ks", "Qd"]}
    board = ["7c", "Kd", "2h", "9s", "Ac"]
    run_scenario(sc(holes, board,
                    [("SB", "raise 200", {"min": 4, "max": 200}),
                     ("BB", "call", {"legal": {"fold", "call"}}),
                     ("SB", "discard 5c", {"street": "flop", "legal": {"discard"}, "pot": 400}),
                     ("BB", "discard Qd", {"legal": {"discard"}})],
                    {"deltas": {"SB": 200, "BB": -200}, "showdown": True, "muck": ["5c", "Qd"]}))


# --------------------------------------------------------------------------- 8.4

def test_ex_8_4_fold_before_the_discard() -> None:
    holes = {"SB": ["As", "5d", "9c"], "BB": ["Kh", "Ks", "Qd"]}
    st = run_scenario(sc(holes, ["Kd", "7s", "3c", "2h", "4c"],
                         [("SB", "call", {}), ("BB", "check", {}),
                          ("BB", "raise 4", {"street": "flop", "pot": 4}),
                          ("SB", "fold", {"pot": 8})],
                         {"deltas": {"SB": -2, "BB": 2}, "folded": "SB", "showdown": False,
                          "muck": [], "hole": {"SB": holes["SB"]}}))
    assert st.deltas == [-2, 2]


# --------------------------------------------------------------------------- 8.5

def test_ex_8_5_kicker() -> None:
    board = parse_cards("Ah,Kd,8c,5s,2h")
    assert EV.evaluate(parse_cards("Ac,Qs"), board) > EV.evaluate(parse_cards("Ad,Js"), board)


def test_ex_8_5_split_pot_both_play_the_board() -> None:
    board = parse_cards("Ts,Js,Qd,Kh,Ac")
    a, b = EV.evaluate(parse_cards("9c,9d"), board), EV.evaluate(parse_cards("4c,4h"), board)
    assert a == b == EV.evaluate(parse_cards("2c,3d"), board)         # none of the hole cards play
    run_scenario(sc({"SB": ["9c", "9d", "2h"], "BB": ["4c", "4h", "3d"]},
                    ["Ts", "Js", "Qd", "Kh", "Ac"],
                    [("SB", "call", {}), ("BB", "check", {}), ("BB", "check", {}),
                     ("SB", "check", {}), ("SB", "discard 2h", {}), ("BB", "discard 3d", {}),
                     ("BB", "check", {}), ("SB", "check", {}), ("BB", "check", {}),
                     ("SB", "check", {})],
                    {"deltas": {"SB": 0, "BB": 0}, "showdown": True}))


# --------------------------------------------------------------------------- 8.6

class Scripted:
    """An in-process player replying from a function; records what it is told."""
    name = "scripted"

    def __init__(self, reply) -> None:
        self.reply, self.msgs = reply, []

    def notify(self, msg) -> None:
        self.msgs.append(msg)

    def act(self, req):
        self.msgs.append(req)
        return self.reply(req)

    def close(self) -> None:
        pass


def passive(req):
    if req.legal.can_special:
        return Action.special("0")
    return Action.check() if req.legal.check else Action.call()


def play(p_sb, p_bb, holes, board=EX1_BOARD):
    rules = to_rules(load_catalog()[SPEC])
    seats = [Seat(p_sb, 60.0), Seat(p_bb, 60.0)]
    return Hand(rules, seats, [200, 200], rigged_deck(rules, holes, board), 0, "fold",
                audit=True).play(), seats


def test_ex_8_6_illegal_discard_discards_the_lowest_card() -> None:
    bad = Scripted(lambda r: Action.special("9") if r.legal.can_special else passive(r))
    res, seats = play(bad, Scripted(passive),
                      {"SB": ["7d", "7s", "Ac"], "BB": ["2h", "3d", "4c"]},
                      ["Kc", "Jd", "Th", "3s", "5d"])
    assert seats[0].errors == 1
    mine = [m for m in bad.msgs if isinstance(m, Info) and m.kind == "reveal" and m.who == "me"]
    assert [format_card(c) for c in mine[0].cards] == ["7s"]        # spades before diamonds


def test_ex_8_6_illegal_raise_becomes_a_check() -> None:
    state = {"n": 0}

    def bb(req):
        if req.legal.can_special or req.legal.call or req.legal.fold:
            return passive(req)
        state["n"] += 1
        return Action.raise_to(1) if state["n"] == 2 else passive(req)   # 2nd check spot: the flop

    res, seats = play(Scripted(passive), Scripted(bb), EX1_HOLES)
    assert seats[1].errors == 1 and res.folded is None and res.showdown


def test_ex_8_6_illegal_check_becomes_a_fold() -> None:
    sb = Scripted(lambda r: Action.raise_to(6) if r.legal.can_raise and r.legal.call else passive(r))
    res, seats = play(sb, Scripted(lambda r: Action.check()), EX1_HOLES)
    assert seats[1].errors == 1 and res.folded == 1 and res.deltas == [2, -2]


# --------------------------------------------------------------------------- the bot side

PS1 = [Action.raise_to(6), Action.raise_to(8), Action.call(), Action.special("2"),
       Action.call(), Action.raise_to(70)]


def test_bot_replays_ex_8_1_with_the_ps_replies() -> None:
    bot = replay_transcript(FIX / "ps_example_1.txt", brain="scripted", adapter="pokerbots",
                            script=PS1)
    h = bot.state.hand
    assert [format_card(c) for c in h.hole] == ["Qh", "Jh"]           # discard_result hole_cards
    assert h.finished and h.delta == 140


def test_bot_handles_ex_8_4_null_opponent_fields() -> None:
    bot = replay_transcript(FIX / "ps_example_4.txt", brain="scripted", adapter="pokerbots",
                            script=[Action.call(), Action.fold()])
    assert bot.state.hand.finished and bot.state.hand.delta == -2


def test_bot_ignores_a_notice_without_replying() -> None:
    lines = [t for _, tag, t in read_transcript(FIX / "ps_example_4.txt") if tag == "E"][:2]
    out = io.StringIO()
    bot = Bot(make_brain("tier0"), out, adapter=get_adapter("pokerbots"))
    for t in lines + ['{"type":"notice","code":"illegal_discard","applied":"7s"}']:
        bot.handle_line(t)
    assert out.getvalue() == ""


def drive_bot_py(fixture: str):
    """Run `bot.py` (the real entry point) over a PS transcript; returns (stdout lines, stderr)."""
    reqs = [(tag, t) for _, tag, t in read_transcript(FIX / fixture) if tag == "E"]
    p = subprocess.Popen([sys.executable, str(ROOT / "bot.py")], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd="/")
    replies, requests = [], []
    for _, text in reqs:
        p.stdin.write(text + "\n")
        p.stdin.flush()
        m = json.loads(text)
        if m["type"] in ("action_request", "discard_request"):
            requests.append(m)
            replies.append(p.stdout.readline())
    out_rest, err = p.communicate(timeout=30)
    return requests, replies, out_rest, err


@pytest.mark.parametrize("fixture", ["ps_example_1.txt", "ps_example_4.txt"])
def test_bot_py_stdout_is_protocol_only_and_every_reply_is_legal(fixture) -> None:
    requests, replies, rest, err = drive_bot_py(fixture)
    assert rest == "" and len(replies) == len(requests) >= 2          # nothing unprompted
    for req, line in zip(requests, replies):
        r = json.loads(line)                                          # a pure JSON line each
        if req["type"] == "discard_request":
            assert r["type"] == "discard" and r["card"] in req["hole_cards"]
        else:
            assert r["type"] == "action" and r["action"] in req["legal_actions"]
            if r["action"] == "raise":
                assert req["min_raise"] <= r["amount"] <= req["max_raise"]
    assert "Traceback" not in err
