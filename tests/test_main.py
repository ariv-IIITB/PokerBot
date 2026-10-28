"""In-process tests of the main loop: safety layers and garbage handling."""
import io
import time

import pytest
from helpers import MALFORMED, decode_replies, encode, protocol_name, scripted_messages

from bot.actions import Action
from bot.brains.base import Brain
from bot.brains.tier0 import Tier0Brain
from bot.main import Bot
from bot.actions import LegalActions
from bot.protocol import ActRequest
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


def run_bot(brain: Brain, msgs, timer: TimeManager | None = None, noise=None):
    """Run the bot on encoded `msgs` (optionally with noise lines interleaved); returns the
    bot and its replies decoded back into Actions."""
    lines = encode(msgs)
    if noise:
        lines = [noise[i % len(noise)] + "\n" + line for i, line in enumerate(lines)]
    out = io.StringIO()
    bot = Bot(brain, out, timer)
    bot.run(io.StringIO("\n".join(lines) + "\n"))
    replies = out.getvalue().splitlines()
    return bot, decode_replies(msgs, replies)


def acts(msgs) -> int:
    return sum(1 for m in msgs if isinstance(m, ActRequest))


F, K, C = Action.fold(), Action.check(), Action.call()
S0 = Action.special("1")   # the discard fallback: lowest card of the scripted hole Ah,Kd


def test_tier0_full_match() -> None:
    msgs = scripted_messages(hands=3)
    bot, replies = run_bot(Tier0Brain(), msgs)
    assert len(replies) == acts(msgs) == 12
    # Per hand: fold (facing bet), check, discard first choice, fold.
    assert replies[:4] == [F, K, S0, F]
    assert bot.state.hands_played == 3 and bot.state.match_over


def test_aggressive_brain_is_clamped() -> None:
    _, replies = run_bot(ScriptedBrain(Action.raise_to(99999)), scripted_messages(hands=1))
    assert replies == [Action.raise_to(400), Action.raise_to(398), S0, Action.raise_to(398)]


def test_brain_exception_falls_back_to_tier0() -> None:
    bot, replies = run_bot(CrashingBrain(), scripted_messages(hands=2))
    assert replies[:4] == [F, K, S0, F]
    assert bot.brain_errors > 0 and bot.state.hands_played == 2


def test_garbage_and_malformed_lines_ignored() -> None:
    noisy = ["", "garbage here", "\x00\xff"] + MALFORMED[protocol_name()]
    bot, replies = run_bot(Tier0Brain(), scripted_messages(hands=1), noise=noisy)
    assert replies == [F, K, S0, F]
    assert bot.bad_lines >= 3


def test_act_with_nothing_legal_still_replies() -> None:
    _, replies = run_bot(Tier0Brain(), [ActRequest(0, 0, 0, 0, LegalActions(), None, 0, 0)])
    assert replies == [F]


def test_emergency_mode_skips_brain() -> None:
    brain = ScriptedBrain(Action.raise_to(50))
    bot, replies = run_bot(brain, scripted_messages(hands=1, timeleft=0.5))
    assert brain.calls == 0 and bot.emergency_decisions == 4
    assert replies == [F, K, S0, F]


@pytest.mark.skipif(not deadline_supported(), reason="needs SIGALRM")
def test_slow_brain_hits_hard_deadline() -> None:
    timer = TimeManager(cfg=TimingConfig(max_budget_s=0.01, hard_min_s=0.02, hard_mult=1.0))
    t0 = time.perf_counter()
    bot, replies = run_bot(SlowBrain(), scripted_messages(hands=1), timer)
    assert time.perf_counter() - t0 < 1.0
    assert bot.deadline_hits == 4
    assert replies == [F, K, S0, F]


def test_eof_without_endmatch_exits_cleanly() -> None:
    msgs = scripted_messages(hands=1)[:-1]
    bot, replies = run_bot(Tier0Brain(), msgs)
    assert len(replies) == 4 and not bot.state.match_over


def test_every_reply_parses() -> None:
    msgs = scripted_messages(hands=5)
    _, replies = run_bot(ScriptedBrain(Action.call()), msgs)
    assert len(replies) == acts(msgs)
