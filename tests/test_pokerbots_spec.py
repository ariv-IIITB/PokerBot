"""Independent check of the engine-side wire lines against docs/rules/protocol.pdf (sections 3,
5, 7): every field, type and invariant the PDF states, validated on seeded lab hands. This does
not go through our bot-side parser, so it cannot agree with a mistake by construction."""
import json

import pytest
from kit.roundtrip import record_match

from bot.cards import format_card
from bot.protocols import get_adapter
from bot.protocols.base import as_lines

CARD = set("23456789TJQKA"), set("shdc")
STREETS = ("preflop", "flop", "turn", "river")


def is_card(c) -> bool:
    return isinstance(c, str) and len(c) == 2 and c[0] in CARD[0] and c[1] in CARD[1]


def reply_line(action, eng) -> str:
    """The bot's reply as the PDF words it (section 6), built here, not by our bot side."""
    if action.kind == "S":
        return json.dumps({"type": "discard", "card": format_card(eng.e_hole[int(action.choice)])})
    name = {"F": "fold", "K": "check", "C": "call", "R": "raise"}[action.kind]
    return json.dumps({"type": "action", "action": name,
                       **({"amount": action.amount} if action.kind == "R" else {})})


def check_history(history, hand, seat) -> None:
    for e in history:
        assert e["street"] in STREETS and e["actor"] in ("me", "opp")
        assert e["action"] in ("fold", "check", "call", "raise"), hand
        assert ("amount" in e) == (e["action"] in ("call", "raise")), e   # amount: call and raise only
        assert set(e) <= {"street", "actor", "action", "amount"}
    # amounts are "to" amounts: a call matches the other side's bet, a raise exceeds it
    bets = {"preflop": {"me": 1, "opp": 2} if seat == "button" else {"me": 2, "opp": 1}}
    for e in history:
        b = bets.setdefault(e["street"], {"me": 0, "opp": 0})
        other = "opp" if e["actor"] == "me" else "me"
        if e["action"] == "call":
            assert e["amount"] == b[other] > b[e["actor"]], (e, history)
            b[e["actor"]] = e["amount"]
        elif e["action"] == "raise":
            assert e["amount"] > b[other], (e, history)
            b[e["actor"]] = e["amount"]


def check_action_request(m, seat, start_stack=200) -> None:
    assert m["street"] in STREETS and all(is_card(c) for c in m["board"])
    assert len(m["board"]) == {"preflop": 0, "flop": 3, "turn": 4, "river": 5}[m["street"]]
    assert m["to_call"] == m["opp_bet"] - m["my_bet"] >= 0
    # pot = every chip both players have committed
    assert m["pot"] == (start_stack - m["my_stack"]) + (start_stack - m["opp_stack"]), m
    legal = m["legal_actions"]
    assert set(legal) <= {"fold", "check", "call", "raise"} and legal
    assert ("fold" in legal) == (m["to_call"] > 0) == ("call" in legal)       # section 7
    assert ("check" in legal) == (m["to_call"] == 0)
    assert ("raise" in legal) == ("min_raise" in m and "max_raise" in m)
    assert 0 <= m["raises_left"] <= 4 and (m["raises_left"] > 0 or "raise" not in legal)
    if "raise" in legal:
        assert m["min_raise"] <= m["max_raise"]
        assert m["max_raise"] == m["my_bet"] + m["my_stack"] or m["max_raise"] == m["opp_bet"] + m["opp_stack"]
    check_history(m["history"], m, seat)
    assert isinstance(m["time_left_ms"], int)


@pytest.mark.parametrize("seed", range(6))
def test_engine_lines_follow_the_pdf(seed) -> None:
    hands_seen = discards = showdowns = folds = allin = 0
    for rec in record_match("discard_holdem", 150, seed):
        eng = get_adapter("pokerbots")
        prev = None
        for ev in rec.events:
            lines = as_lines(eng.encode_message(ev[1]))
            if ev[0] == "act":                      # the bot's reply: the engine records it
                eng.parse_action(reply_line(ev[2], eng))
            for line in lines:
                m = json.loads(line)
                t = m["type"]
                if t == "init":
                    assert m["protocol_version"] == "1.0" and m["starting_stack"] == 200
                    assert (m["small_blind"], m["big_blind"]) == (1, 2)
                elif t == "new_hand":
                    hands_seen += 1
                    seat = m["seat"]
                    assert m["seat"] in ("button", "big_blind") and len(m["hole_cards"]) == 3
                    assert all(is_card(c) for c in m["hole_cards"]) and m["hand_id"] >= 1
                    assert m["stack"] == 200 == m["opp_stack"]            # "before blinds"
                elif t == "action_request":
                    check_action_request(m, seat)
                    if m["my_stack"] == 0 or m["opp_stack"] == 0:
                        allin += 1
                elif t == "discard_request":
                    discards += 1
                    assert len(m["hole_cards"]) == 3 and len(m["board"]) == 3
                    assert m["pot"] == 400 - m["my_stack"] - m["opp_stack"]
                    assert isinstance(m["time_left_ms"], int)
                elif t == "discard_result":
                    assert m["my_discard"] not in m["hole_cards"] and len(m["hole_cards"]) == 2
                    assert is_card(m["opp_discard"]) and m["opp_discard"] != m["my_discard"]
                elif t == "hand_result":
                    assert m["result"] in ("fold", "showdown")
                    assert (m["result"] == "showdown") == (m["opp_hole_cards"] is not None)
                    if m["result"] == "showdown":
                        showdowns += 1
                        assert len(m["board"]) == 5 and len(m["opp_hole_cards"]) == 2
                        assert len(m["my_hole_cards"]) == 2
                    else:
                        folds += 1
                        assert m["history"][-1]["action"] == "fold"
                    # 3 cards if the hand ended before the discard, else 2 and the opp discard shown
                    assert len(m["my_hole_cards"]) == (2 if m["opp_discard"] else 3)
                    assert isinstance(m["net"], int)
                    check_history(m["history"], m, seat)
                prev = m
    assert hands_seen > 250 and discards > 50 and showdowns > 10 and folds > 10 and allin > 5
