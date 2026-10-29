"""Phase C: the official wire format (docs/rules/protocol.pdf) as an adapter, both directions."""
import io
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from kit.roundtrip import check_round_trip
from kit.scenario import load_spec
from kit.transcript import read_transcript, replay_transcript

from bot.actions import Action
from bot.cards import format_card, parse_card, parse_cards
from bot.game.rules_spec import to_rules
from bot.main import Bot
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, MatchInfo,
                          OppAction, ProtocolError, Showdown)
from bot.protocols import ADAPTERS, DEFAULT, get_adapter
from bot.protocols.base import as_messages
from bot.sim.replay import reconstruct
from kit.scripted_brain import ScriptedBrain
from lab.engine import play_match
from lab.players import PlayerSpec, SubprocessPlayer

FIXTURE = Path(__file__).parent / "fixtures" / "protocol" / "example_hand.txt"
ROOT = Path(__file__).resolve().parent.parent
PDF_REPLIES = [Action.raise_to(6), Action.raise_to(6), Action.special("1"), Action.check(),
               Action.raise_to(10)]                 # raise 6, raise 6, discard Kd, check, raise 10


def run_example(**kw) -> Bot:
    return replay_transcript(FIXTURE, brain="scripted", adapter="pokerbots", script=PDF_REPLIES, **kw)


def test_it_is_registered_and_the_default() -> None:
    assert "pokerbots" in ADAPTERS and DEFAULT == "pokerbots"
    assert get_adapter("pokerbots").name == "pokerbots"


# --------------------------------------------------------------------------- Protocol section 10

def test_example_hand_transcript() -> None:
    bot = run_example()
    h = bot.state.hand
    assert h.finished and h.delta == 12 and bot.state.bankroll == 12
    assert [format_card(c) for c in h.hole] == ["As", "7c"]
    reveals = [(i.who, format_card(i.cards[0])) for i in h.info if i.kind == "reveal"]
    assert sorted(reveals) == [("me", "Kd"), ("opp", "Qs")]
    assert bot.state.match.hands == 400 and bot.state.match.timebank == 60.0
    assert bot.adapter.per_response_s == 5.0
    assert bot.state.match_over


def test_example_hand_neutral_history_matches_the_lab_engine() -> None:
    """What the brain sees: our actions, the opponent's (the discard-time ones inferred)."""
    h = run_example().state.hand
    seen = [(r.street, r.actor, r.action.kind, r.action.amount) for r in h.history]
    assert seen == [(0, "me", "R", 6), (0, "opp", "C", None), (1, "opp", "K", None),
                    (1, "me", "R", 6), (1, "opp", "C", None), (1, "me", "S", None),
                    (1, "opp", "S", None), (2, "opp", "K", None), (2, "me", "K", None),
                    (3, "opp", "K", None), (3, "me", "R", 10), (3, "opp", "F", None)]


def test_replies_decode_on_the_engine_side() -> None:
    """The kit already ran parse_action over every B> line; check a few by hand too."""
    a = get_adapter("pokerbots")
    a.parse_line(next(t for _, k, t in read_transcript(FIXTURE) if k == "E" and "new_hand" in t))
    assert a.encode_action(Action.raise_to(40)) == '{"type":"action","action":"raise","amount":40}'
    assert a.encode_action(Action.fold()) == '{"type":"action","action":"fold"}'
    assert a.encode_action(Action.special("2")) == '{"type":"discard","card":"7c"}'


def test_unknown_fields_everywhere_change_nothing(tmp_path) -> None:
    noisy = tmp_path / "noisy.txt"
    lines = []
    for _, tag, text in read_transcript(FIXTURE):
        if tag == "E":
            obj = json.loads(text)
            obj.update(future_field=[1, 2], another={"x": 1})
            for entry in obj.get("history", []):
                entry["extra"] = True
            text = json.dumps(obj)
        lines.append(f"{tag}> {text}")
    lines.insert(2, "E> " + json.dumps({"type": "some_future_message", "x": 1}))
    noisy.write_text("\n".join(lines) + "\n")
    bot = replay_transcript(noisy, brain="scripted", adapter="pokerbots", script=PDF_REPLIES)
    assert bot.state.hand.delta == 12 and bot.bad_lines == 0


# --------------------------------------------------------------------------- robustness

def feed(lines):
    out = io.StringIO()
    bot = Bot(ScriptedBrain(), out, adapter=get_adapter("pokerbots"))
    for line in lines:
        bot.handle_line(line)
    return bot, out.getvalue()


def example_lines(upto: str) -> list[str]:
    lines = []
    for _, tag, text in read_transcript(FIXTURE):
        if tag == "E":
            lines.append(text)
            if upto in text:
                break
    return lines


def test_malformed_input_never_crashes_or_replies() -> None:
    start = example_lines('"new_hand"')
    bad = ["", "   ", "not json", "[1, 2]", "42", '{"type": "action_request"}',
           '{"type":"new_hand","hand_id":"x"}', '{"type":"discard_request","hand_id":1}',
           '{"type":"init"}', '{"type":"hand_result","hand_id":1}', "\x00\xff",
           '{"type":"action_request","hand_id":1,"street":"flop","board":["Zz"],"pot":1,'
           '"my_bet":0,"opp_bet":0,"to_call":0,"my_stack":1,"opp_stack":1,'
           '"legal_actions":["check"],"history":[],"time_left_ms":5}']
    bot, out = feed(start + bad)
    # every broken known message is rejected; only the broken *request* gets a (safe) answer
    assert out.splitlines() == ['{"type":"action","action":"check"}',
                                '{"type":"discard","card":"7c"}',
                                '{"type":"action","action":"check"}'] and bot.bad_lines >= 9


def test_a_broken_request_still_gets_a_safe_reply() -> None:
    """A missing reply forfeits the match; a blind check is corrected by the engine if illegal."""
    start = example_lines('"new_hand"')
    broken_action = '{"type":"action_request","hand_id":1,"street":"flop"}'
    broken_discard = '{"type":"discard_request","hand_id":1,"board":["Ah","7d","2s"]}'
    bot, out = feed(start + [broken_action, broken_discard, '{"type":"action_request", broken json'])
    assert out.splitlines() == ['{"type":"action","action":"check"}',
                                '{"type":"discard","card":"7c"}',      # our lowest card (As Kd 7c)
                                '{"type":"action","action":"check"}']
    bot, out = feed(start + ['{"type":"notice"'])        # not a request: silence
    assert out == ""


def test_parse_errors_are_protocol_errors() -> None:
    a = get_adapter("pokerbots")
    for line in ("not json", "[1]", '{"type":"init"}', '{"type":"new_hand","seat":"nobody"}',
                 '{"type":"action_request","legal_actions":"fold"}'):
        with pytest.raises(ProtocolError):
            a.parse_line(line)
    for line in ("", "  ", '{"type":"banana"}', '{"no_type": 1}', '{"type":"notice","code":"x"}'):
        assert a.parse_line(line) is None


def test_unknown_type_blank_and_notice_get_no_reply() -> None:
    bot, out = feed(example_lines('"new_hand"') + ['{"type":"nope"}', "", "\n",
                    '{"type":"notice","code":"illegal_action","applied":"fold"}'])
    assert out == "" and bot.bad_lines == 0


def test_never_replies_without_a_request() -> None:
    bot, out = feed(example_lines("discard_result"))
    replies = [ln for ln in out.splitlines() if ln]
    assert len(replies) == 3                            # raise, raise, discard: one per request
    # a hand_result / match_end must not produce output either
    bot, out = feed(example_lines("match_end"))
    assert len([ln for ln in out.splitlines() if ln]) == 5


def test_a_reply_in_the_wrong_state_is_still_legal_json() -> None:
    a = get_adapter("pokerbots")
    assert json.loads(a.encode_action(Action.call())) == {"type": "action", "action": "call"}
    # no hole cards known yet: a discard still produces a well-formed line, never an exception
    assert json.loads(a.encode_action(Action.special("1")))["type"] == "discard"


# --------------------------------------------------------------------------- the stream the brain sees

def neutral_stream(upto: str) -> list:
    """The neutral messages for the example up to the first line containing `upto`, answering
    each request with the PDF's reply (the adapter notes what we sent)."""
    a, replies, out = get_adapter("pokerbots"), iter(PDF_REPLIES), []
    for text in example_lines(upto):
        for m in as_messages(a.parse_line(text)):
            out.append(m)
            if isinstance(m, ActRequest) and upto not in text:
                a.encode_action(next(replies))
    return out


def test_new_hand_and_init_map_to_neutral_messages() -> None:
    msgs = neutral_stream('"new_hand"')
    assert msgs[0] == MatchInfo(hands=400, timebank=60.0, sb=1, bb=2, stack=200)
    assert msgs[1] == HandStart(0, 0, 200, 200)          # wire hand 1 = neutral hand 0, seat button
    assert msgs[2] == HoleCards(parse_cards("As,Kd,7c"))


def test_street_changes_come_before_the_actions_on_the_new_street() -> None:
    msgs = neutral_stream('"street":"flop"')
    kinds = [type(m).__name__ for m in msgs[3:]]
    # preflop request; then their call (preflop), the flop, their check (flop), the flop request
    assert kinds == ["ActRequest", "OppAction", "BoardUpdate", "OppAction", "ActRequest"]
    assert msgs[4].action == Action.call() and msgs[6].action == Action.check()
    assert msgs[5] == BoardUpdate(1, parse_cards("Ah,7d,2s"))


def test_discard_request_infers_the_opponents_flop_closer() -> None:
    msgs = neutral_stream("discard_request")
    assert isinstance(msgs[-1], ActRequest) and msgs[-1].legal.special.choices == ("0", "1", "2")
    assert msgs[-2] == OppAction(Action.call())          # they called our flop raise
    assert msgs[-1].mybet == 6 and msgs[-1].oppbet == 6 and msgs[-1].pot == 24


def test_discard_result_matches_the_engines_order_per_seat() -> None:
    a = get_adapter("pokerbots")
    a.parse_line(json.dumps({"type": "new_hand", "hand_id": 1, "seat": "button",
                             "hole_cards": ["As", "Kd", "7c"], "stack": 200, "opp_stack": 200}))
    res = json.dumps({"type": "discard_result", "hand_id": 1, "my_discard": "Kd",
                      "opp_discard": "Qs", "hole_cards": ["As", "7c"]})
    kinds = [type(m).__name__ for m in as_messages(a.parse_line(res))]
    assert kinds == ["HoleCards", "Info", "OppAction", "Info"]          # button: its discard first
    b = get_adapter("pokerbots")
    b.parse_line(json.dumps({"type": "new_hand", "hand_id": 1, "seat": "big_blind",
                             "hole_cards": ["Qs", "9h", "9c"], "stack": 200, "opp_stack": 200}))
    kinds = [type(m).__name__ for m in as_messages(b.parse_line(res))]
    assert kinds == ["OppAction", "Info", "HoleCards", "Info"]


def test_hand_result_adds_what_the_history_never_showed() -> None:
    """A showdown after an all-in: the last opponent action, the run-out board, the cards."""
    a = get_adapter("pokerbots")
    a.parse_line(json.dumps({"type": "new_hand", "hand_id": 1, "seat": "button",
                             "hole_cards": ["As", "Kd", "7c"], "stack": 200, "opp_stack": 200}))
    result = {"type": "hand_result", "hand_id": 1, "result": "showdown", "net": 200,
              "board": ["Ah", "7d", "2s", "3c", "4h"], "my_hole_cards": ["As", "7c"],
              "opp_hole_cards": ["9h", "9c"], "opp_discard": "Qs",
              "history": [{"street": "preflop", "actor": "me", "action": "raise", "amount": 200},
                          {"street": "preflop", "actor": "opp", "action": "call", "amount": 200}]}
    msgs = as_messages(a.parse_line(json.dumps(result)))
    assert [type(m).__name__ for m in msgs] == ["OppAction", "BoardUpdate", "BoardUpdate",
                                                "BoardUpdate", "Showdown", "HandEnd"]
    assert msgs[-2] == Showdown(parse_cards("9h,9c")) and msgs[-1] == HandEnd(200)


# --------------------------------------------------------------------------- the dead card

def test_the_opponents_discard_is_dead_in_the_reconstruction() -> None:
    """At the turn decision, Qs is mapped to the opponent's discarded slot: it is never in
    their sampled hole cards and never dealt."""
    rules = to_rules(load_spec("discard_holdem"))
    rng = np.random.default_rng(5)
    found = {}

    class Recon(ScriptedBrain):
        def decide(self, state, legal, budget_s):
            action = super().decide(state, legal, budget_s)
            if self.calls == 4:                              # the turn decision
                found["rec"] = reconstruct(rules, state.hand, rng)
            return action

    bot = Bot(Recon(PDF_REPLIES), io.StringIO(), adapter=get_adapter("pokerbots"))
    for text in example_lines('"street":"turn"'):
        bot.handle_line(text)
    rec, qs = found["rec"], parse_card("Qs")
    assert qs in rec.mapping.values() and qs not in rec.pool
    for _ in range(50):
        world = rec.world(rng)
        opp = world.hole[1 - rec.me]
        assert qs not in opp and qs not in world.deck and qs not in world.board
        assert len(opp) == 2 and qs in world.muck


# --------------------------------------------------------------------------- round trips

@pytest.mark.parametrize("seed", [0, 1, 2])
def test_round_trip_discard_holdem_200_hands(seed) -> None:
    rep = check_round_trip("pokerbots", "discard_holdem", hands=200, seed=seed)
    assert min(rep.seats) > 100                          # both seats, folds, all-ins, showdowns


# --------------------------------------------------------------------------- engine side

def test_the_lab_can_seat_any_pokerbots_bot_as_a_subprocess() -> None:
    p = SubprocessPlayer([sys.executable, "-m", "bot.main", "--brain", "tier0"],
                         protocol="pokerbots")
    try:
        r = play_match([p, PlayerSpec.brain("calling_station").build()], load_spec("discard_holdem"),
                       seed=3, hands=40, audit=True)
    finally:
        p.close()
    assert r.forfeit is None and r.errors == [0, 0] and r.hands_played == 40


def test_engine_adapter_applies_the_engines_corrections_to_its_history() -> None:
    """An illegal reply is recorded as what the engine applies (check, else fold), not as sent."""
    a = get_adapter("pokerbots")
    a.encode_message(MatchInfo())
    a.encode_message(HandStart(0, 0, 200, 200))
    a.encode_message(HoleCards(parse_cards("As,Kd,7c")))
    from bot.actions import LegalActions
    a.encode_message(ActRequest(3, 1, 199, 198, LegalActions(fold=True, call=True, raise_min=4,
                                                              raise_max=200), 60.0, 1, 2))
    assert a.parse_action('{"type":"action","action":"raise","amount":1}') == Action.raise_to(1)
    assert a.e_history[-1] == {"street": "preflop", "actor": "me", "action": "fold"}
    with pytest.raises(ProtocolError):
        a.parse_action("garbage")
    assert a.e_history[-1]["action"] == "fold"


# --------------------------------------------------------------------------- full matches, real protocol

def bot_player(name: str, brain: str, tmp_path) -> tuple:
    err = tmp_path / f"{name}.err"
    return SubprocessPlayer([sys.executable, "-m", "bot.main", "--brain", brain], name=name,
                            stderr_to=str(err), protocol="pokerbots"), err


def play_real(tmp_path, brain_a, brain_b, hands, seed=1):
    a, ea = bot_player("a", brain_a, tmp_path)
    b, eb = bot_player("b", brain_b, tmp_path)
    r = play_match([a, b], load_spec("discard_holdem"), seed=seed, hands=hands, audit=True,
                   time_bank_s=hands * 0.15)          # the real pace: 60 s per 400 hands
    return r, ea.read_text(), eb.read_text()


def assert_clean(r, hands, *stderr) -> None:
    assert r.hands_played == hands and r.forfeit is None
    assert r.errors == [0, 0]                         # no illegal reply: so the engine sends no notice
    for text in stderr:
        assert "WARN" not in text, text[:500]         # the bots saw no malformed line either


def test_full_match_tier1_vs_tier2_over_the_real_protocol(tmp_path) -> None:
    r, ea, eb = play_real(tmp_path, "tier1", "tier2", hands=60)
    assert_clean(r, 60, ea, eb)


@pytest.mark.slow
def test_full_400_hand_match_our_bot_vs_our_bot_over_the_real_protocol(tmp_path) -> None:
    r, ea, eb = play_real(tmp_path, "tier2", "tier2", hands=400)
    assert_clean(r, 400, ea, eb)
    assert min(r.bank_left) > 0


def test_starter_bot_plays_a_match_over_the_real_protocol(tmp_path) -> None:
    starter = PlayerSpec.subprocess([sys.executable, str(ROOT / "lab" / "sparring" / "starter_bot.py")],
                                    label="starter", protocol="pokerbots").build()
    ours, err = bot_player("ours", "tier1", tmp_path)
    r = play_match([ours, starter], load_spec("discard_holdem"), seed=5, hands=80, audit=True,
                   time_bank_s=12.0)
    assert_clean(r, 80, err.read_text())
    assert r.chips[0] > 0                             # the starter checks/calls everything
