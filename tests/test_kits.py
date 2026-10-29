"""Examples that exercise the test kits (tests/kit/): one scenario, one transcript, one round trip."""
import pytest
from kit.scenario import Scenario, ScenarioError, run_scenario

HOLDEM_HAND = Scenario(
    spec="holdem_nl",
    holes={"SB": ["As", "Kd"], "BB": ["Qs", "9h"]},
    board=["Ah", "7d", "2s", "3c", "4h"],
    steps=[
        ("SB", "raise 6", {"legal": {"fold", "call", "raise"}, "min": 4, "max": 400,
                           "street": "preflop", "pot": 3, "tocall": 1}),
        ("BB", "call", {"tocall": 4}),
        ("BB", "check", {"street": "flop", "pot": 12, "legal": {"check", "raise"}}),
        ("SB", "raise 6", {"min": 2}),
        ("BB", "call", {"tocall": 6}),
        ("BB", "check", {"street": "turn", "pot": 24}),
        ("SB", "check", {}),
        ("BB", "check", {"street": "river"}),
        ("SB", "raise 10", {}),
        ("BB", "fold", {"tocall": 10}),
    ],
    expect={"deltas": {"SB": 12, "BB": -12}, "showdown": False, "folded": "BB", "pot": 34},
)


def test_scenario_holdem_hand() -> None:
    run_scenario(HOLDEM_HAND)


def test_scenario_names_the_failing_step() -> None:
    bad = Scenario(HOLDEM_HAND.spec, HOLDEM_HAND.holes, HOLDEM_HAND.board,
                   [("SB", "raise 6", {"min": 5})])
    with pytest.raises(ScenarioError, match=r"step 0 \(SB: raise 6\).*min=5.*got 4"):
        run_scenario(bad)
    wrong_actor = Scenario(HOLDEM_HAND.spec, HOLDEM_HAND.holes, HOLDEM_HAND.board,
                           [("BB", "check", {})])
    with pytest.raises(ScenarioError, match="SB is to act"):
        run_scenario(wrong_actor)


def test_scenario_showdown_pays_the_better_hand() -> None:
    s = Scenario("holdem_nl", HOLDEM_HAND.holes, HOLDEM_HAND.board,
                 [("SB", "call", {}), ("BB", "check", {})]
                 + [(a, "check", {}) for _ in range(3) for a in ("BB", "SB")],
                 {"deltas": {"SB": 2, "BB": -2}, "showdown": True})
    run_scenario(s)


# --------------------------------------------------------------------------- transcript kit
from pathlib import Path

from kit.transcript import TranscriptError, replay_transcript

from bot.actions import Action

FIXTURES = Path(__file__).parent / "fixtures" / "protocol"


def test_placeholder_transcript() -> None:
    bot = replay_transcript(FIXTURES / "placeholder_hand.txt", brain="scripted",
                            script=[Action.raise_to(6), Action.special("1"), Action.check()])
    h = bot.state.hand
    assert h.finished and h.delta == 12
    assert [r.action.kind for r in h.history if r.actor == "me"] == ["R", "S", "K"]


def test_transcript_catches_a_wrong_reply(tmp_path) -> None:
    f = tmp_path / "bad.txt"
    f.write_text("E> MATCH hands=2 timebank=60.0\nE> HAND id=0 seat=0 stack=400 oppstack=400\n"
                 "E> ACT pot=3 tocall=1 mystack=399 oppstack=398 legal=F,C,R:4-400 mybet=1 "
                 "oppbet=2\nB> C\n")
    with pytest.raises(TranscriptError, match="expected reply 'C'"):
        replay_transcript(f)           # Tier 0 folds
    f.write_text("E> MATCH hands=2 timebank=60.0\nB> K\n")
    with pytest.raises(TranscriptError, match="expected 1 reply"):
        replay_transcript(f)           # a reply with no request


# --------------------------------------------------------------------------- round trip
from kit.roundtrip import RoundTripError, check_round_trip

from bot.protocols import ADAPTERS


@pytest.mark.parametrize("adapter", sorted(ADAPTERS))
@pytest.mark.parametrize("spec", ["holdem_nl", "pineapple", "exposed_hole", "discard_holdem",
                                  str(FIXTURES.parent / "specs" / "public_discard.json")])
def test_round_trip(adapter, spec) -> None:
    if adapter == "pokerbots" and spec in ("pineapple", "exposed_hole"):
        pytest.skip("the official format carries Discard Hold'em only")
    rep = check_round_trip(adapter, spec, hands=30, seed=1)
    assert rep.requests > 30


def test_round_trip_reports_the_first_mismatch(monkeypatch) -> None:
    from bot.protocols.placeholder import PlaceholderAdapter
    real = PlaceholderAdapter.parse_line

    def lossy(self, line):                    # drops the pot from every ACT
        m = real(self, line)
        return m if not hasattr(m, "pot") else type(m)(0, *[getattr(m, f) for f in
                ("tocall", "mystack", "oppstack", "legal", "timeleft", "mybet", "oppbet")])

    monkeypatch.setattr(PlaceholderAdapter, "parse_line", lossy)
    with pytest.raises(RoundTripError, match="state differs on \\['pot'\\]"):
        check_round_trip("placeholder", "holdem_nl", hands=5, seed=0)
