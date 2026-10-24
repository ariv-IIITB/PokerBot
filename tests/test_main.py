"""In-process tests of the main loop: safety layers and garbage handling."""
import io
import time

import pytest
from helpers import scripted_match

from bot.actions import Action
from bot.brains.base import Brain
from bot.brains.tier0 import Tier0Brain
from bot.main import Bot
from bot.protocol import parse_action
from bot.timing import TimeManager, TimingConfig, deadline_supported


class ScriptedBrain(Brain):
    """Always tries the same action; counts calls."""

    def __init__(self, action) -> None:
        self.action = action
        self.calls = 0

    def decide(self, state, legal, budget_s):
        self.calls += 1
        return self.action


class CrashingBrain(Brain):
    def decide(self, state, legal, budget_s):
        raise RuntimeError("boom")

    def observe(self, state, msg):
        raise KeyError("observe boom")


class SlowBrain(Brain):
    def decide(self, state, legal, budget_s):
        time.sleep(5)
        return Action.raise_to(10**6)


def run_bot(brain: Brain, lines: list[str], timer: TimeManager | None = None) -> tuple[Bot, list[str]]:
    out = io.StringIO()
    bot = Bot(brain, out, timer)
    bot.run(io.StringIO("\n".join(lines) + "\n"))
    return bot, out.getvalue().splitlines()


def acts(lines: list[str]) -> int:
    return sum(1 for line in lines if line.startswith("ACT"))


def test_tier0_full_match() -> None:
    lines = scripted_match(hands=3)
    bot, replies = run_bot(Tier0Brain(), lines)
    assert len(replies) == acts(lines) == 12
    # Per hand: fold (facing bet), check, discard first choice, fold.
    assert replies[:4] == ["F", "K", "S 0", "F"]
    assert bot.state.hands_played == 3 and bot.state.match_over


def test_aggressive_brain_is_clamped() -> None:
    _, replies = run_bot(ScriptedBrain(Action.raise_to(99999)), scripted_match(hands=1))
    assert replies == ["R 400", "R 398", "S 0", "R 398"]


def test_brain_exception_falls_back_to_tier0() -> None:
    bot, replies = run_bot(CrashingBrain(), scripted_match(hands=2))
    assert replies[:4] == ["F", "K", "S 0", "F"]
    assert bot.brain_errors > 0 and bot.state.hands_played == 2


def test_garbage_and_malformed_lines_ignored() -> None:
    lines = scripted_match(hands=1)
    noisy = ["", "garbage here", "ACT pot=oops", "HOLE cards=ZZ", "\x00\xff", "MATCH hands=x"]
    mixed = [noisy[i % len(noisy)] + "\n" + line for i, line in enumerate(lines)]
    bot, replies = run_bot(Tier0Brain(), mixed)
    assert replies == ["F", "K", "S 0", "F"]
    assert bot.bad_lines >= 3


def test_act_with_nothing_legal_still_replies() -> None:
    _, replies = run_bot(Tier0Brain(), ["ACT pot=0 tocall=0 mystack=0 oppstack=0 legal=-"])
    assert replies == ["F"]


def test_emergency_mode_skips_brain() -> None:
    brain = ScriptedBrain(Action.raise_to(50))
    lines = scripted_match(hands=1)
    lines = [line.replace("timeleft=50.0000", "timeleft=0.5000") for line in lines]
    bot, replies = run_bot(brain, lines)
    assert brain.calls == 0 and bot.emergency_decisions == 4
    assert replies == ["F", "K", "S 0", "F"]


@pytest.mark.skipif(not deadline_supported(), reason="needs SIGALRM")
def test_slow_brain_hits_hard_deadline() -> None:
    timer = TimeManager(cfg=TimingConfig(max_budget_s=0.01, hard_min_s=0.02, hard_mult=1.0))
    t0 = time.perf_counter()
    bot, replies = run_bot(SlowBrain(), scripted_match(hands=1), timer)
    assert time.perf_counter() - t0 < 1.0
    assert bot.deadline_hits == 4
    assert replies == ["F", "K", "S 0", "F"]


def test_eof_without_endmatch_exits_cleanly() -> None:
    lines = scripted_match(hands=1)[:-1]
    bot, replies = run_bot(Tier0Brain(), lines)
    assert len(replies) == 4 and not bot.state.match_over


def test_every_reply_parses() -> None:
    _, replies = run_bot(ScriptedBrain(Action.call()), scripted_match(hands=5))
    for r in replies:
        parse_action(r)
