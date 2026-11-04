"""X1: trait tests on the opponent (bot/strategy/traits.py), fed like bot/opponent.py.

The recorded matches in tests/fixtures/opp_records/ (X0) are replayed through the same path the
bot uses (OppAction messages with the hand history so far), one fresh detector per match.
Targets from the book (section 2.9): over-folder "yes" for the exploiter, rules and conv_opp3; "no"
for stations and aggressors; station "yes" for starter and calling_station.
"""
import math
import random
from pathlib import Path

import pytest

from bot.actions import Action
from bot.opponent import Opponent
from bot.protocol import HandEnd, OppAction
from bot.state import ME, OPP, ActionRecord, GameState, HandState
from bot.strategy import traits as T
from lab.opps import record
from lab.opps import traits as lab_traits

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "opp_records"


def rec(street, who, kind, amount=None):
    return ActionRecord(street, ME if who == "m" else OPP, Action(kind, amount))


# --------------------------------------------------------------------------- the tests' maths

def test_sprt_bounds_and_steps() -> None:
    assert T.UPPER == pytest.approx(math.log(19)) and T.LOWER == pytest.approx(-math.log(19))
    t = T.SPRT(T.SPECS["overfolder"])
    for _ in range(7):
        t.add(True)
    assert t.verdict == "open"                 # 7 x log(1.5) = 2.84 < 2.94
    t.add(True)
    assert t.verdict == "yes" and t.decided_at == 8
    t2 = T.SPRT(T.SPECS["overfolder"])
    for _ in range(8):
        t2.add(False)
    assert t2.verdict == "no"


def test_shrunk_rate_starts_at_the_prior() -> None:
    t = T.SPRT(T.SPECS["station"])
    assert t.rate == pytest.approx(0.5)
    for x in (True,) * 10:
        t.add(x)
    assert t.rate == pytest.approx((10 + 0.5 * 15) / 25)


def test_cusum_restarts_a_decided_trait_when_the_style_changes() -> None:
    """Folds 75% for 100 decisions, then 20%: the alarm comes within 40 decisions of the switch."""
    rnd = random.Random(4)
    t = T.SPRT(T.SPECS["overfolder"])
    for _ in range(100):
        t.add(rnd.random() < 0.75)
    assert t.verdict == "yes" and t.alarms == 0
    for i in range(1, 41):
        t.add(rnd.random() < 0.20)
        if t.alarms:
            break
    assert t.alarms == 1, "no alarm within 40 decisions of the switch"
    for _ in range(60):
        t.add(rnd.random() < 0.20)
    assert t.verdict == "no"


@pytest.mark.parametrize("seed", range(20))
def test_cusum_rarely_alarms_on_a_steady_folder(seed: int) -> None:
    rnd = random.Random(seed)
    t = T.SPRT(T.SPECS["overfolder"])
    for _ in range(300):                       # about a match's worth of postflop decisions
        t.add(rnd.random() < 0.70)
    assert t.alarms == 0 and t.verdict == "yes"


# --------------------------------------------------------------------------- events

def test_classify_reads_the_context_of_the_last_opponent_action() -> None:
    h = [rec(0, "m", "R", 5), rec(0, "o", "F")]
    assert T.classify(h) == T.Event(0, "F", True, True)
    h = [rec(0, "o", "C"), rec(0, "m", "R", 8), rec(0, "o", "C")]      # facing our iso-raise
    assert T.classify(h) == T.Event(0, "C", True, False)
    h = [rec(0, "m", "R", 5), rec(0, "o", "C"), rec(1, "o", "K"), rec(1, "m", "R", 4),
         rec(1, "o", "R", 12), rec(1, "m", "C"), rec(1, "m", "S"), rec(1, "o", "S"),
         rec(2, "o", "K")]
    assert T.classify(h) == T.Event(2, "K", False, False)
    assert T.classify(h[:5]) == T.Event(1, "R", True, False)
    assert T.classify(h[:4]) is None                                    # our action
    assert T.classify(h[:8]) is None                                    # a discard


def test_observations_map_events_to_traits() -> None:
    assert T.observations(T.Event(3, "C", True, False)) == {"overfolder": False, "station": True}
    assert T.observations(T.Event(1, "F", True, False)) == {"overfolder": True}
    assert T.observations(T.Event(0, "F", True, True)) == {"preflop_folder": True}
    assert T.observations(T.Event(2, "R", False, False)) == {}


def _fixture(name: str) -> dict:
    return record.load(FIXTURES / f"{name}.json.gz")


def test_bot_events_equal_the_lab_profile_definitions_on_every_fixture_hand() -> None:
    """The bot's classify and X0's lab.opps.traits agree on every opponent decision."""
    checked = 0
    for path in sorted(FIXTURES.glob("*.json.gz")):
        for hand in record.iter_hands(record.load(path)):
            hs = record.to_hand_state(hand)
            ours = [T.classify(hs.history[:i + 1]) for i in range(len(hs.history))]
            ours = [(e.street, e.kind, e.facing) for e in ours if e is not None]
            lab = [(d.street, d.kind, d.facing) for d in lab_traits.opp_decisions(hand)]
            # postflop "facing our bet" must agree; preflop the lab table does not use it
            assert [e for e in ours if e[0] > 0] == [e for e in lab if e[0] > 0]
            assert [(s, k) for s, k, _f in ours] == [(s, k) for s, k, _f in lab]
            checked += len(lab)
    assert checked > 50_000


# --------------------------------------------------------------------------- replays

def replay_match(hands: list, opponent: Opponent) -> list[dict]:
    """Feed one recorded match through Opponent.observe as the bot would; returns the trait
    verdicts after every hand."""
    state = GameState()
    timeline = []
    for hand in hands:
        full = record.to_hand_state(hand)
        h = HandState(hand_id=full.hand_id, seat=full.seat, start_stack=200, opp_start_stack=200)
        state.hand = h
        for r in full.history:
            h.history.append(r)
            if r.actor == OPP:
                opponent.observe(state, OppAction(r.action), rng=None)
        opponent.observe(state, HandEnd(full.delta or 0), rng=None)
        timeline.append({k: v.verdict for k, v in opponent.traits.state().items()})
    return timeline


def verdicts(name: str, trait: str) -> list[tuple[str, int]]:
    """(final verdict, hand of the last verdict change) per fixture match."""
    out = []
    for pair in _fixture(name)["pairs"]:
        for m in pair["matches"]:
            tl = replay_match(m["hands"], Opponent())
            final = tl[-1][trait]
            first = next((i + 1 for i, v in enumerate(tl) if v[trait] == final
                          and all(w[trait] == final for w in tl[i:])), len(tl))
            out.append((final, first))
    return out


@pytest.mark.parametrize("name,budget", [("d_new_exploiter", 120), ("d_new_rules", 120),
                                         ("d_conv_opp3", 250)])
def test_overfolders_are_caught(name: str, budget: int) -> None:
    v = verdicts(name, "overfolder")
    assert all(final == "yes" for final, _ in v), v
    assert sorted(h for _, h in v)[len(v) // 2 - 1] <= budget, v     # lower median within budget


@pytest.mark.parametrize("name", ["starter", "calling_station", "d_new_lag", "maniac"])
def test_stations_and_aggressors_are_not_overfolders(name: str) -> None:
    v = verdicts(name, "overfolder")
    assert all(final == "no" for final, _ in v), v


@pytest.mark.parametrize("name", ["starter", "calling_station"])
def test_stations_are_caught(name: str) -> None:
    v = verdicts(name, "station")
    assert all(final == "yes" for final, h in v) and max(h for _, h in v) <= 100, v


@pytest.mark.parametrize("name", ["d_new_exploiter", "d_new_rules", "d_conv_opp3"])
def test_overfolders_are_not_stations(name: str) -> None:
    v = verdicts(name, "station")
    assert all(final == "no" for final, _ in v), v


def test_a_broken_trait_test_never_reaches_the_bot() -> None:
    opp = Opponent()

    class Boom:
        def update(self, state, msg):
            raise RuntimeError("boom")

    opp.traits = Boom()
    state = GameState()
    state.hand = HandState(hand_id=1, seat=0, start_stack=200, opp_start_stack=200)
    state.hand.history.append(rec(0, "o", "C"))
    opp.observe(state, OppAction(Action("C")), rng=None)     # must not raise
