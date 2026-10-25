"""Bot entry point: stdin lines -> protocol -> state/brain -> one action line on stdout.

Run as `python -m bot.main [--brain NAME] [--protocol NAME] [--verbose]` or
`python bot/main.py ...`. The wire format comes from bot/protocols/ (default: placeholder,
or $POKERBOT_PROTOCOL).

Safety layers (see CLAUDE.md):
  1. the brain runs inside try/except; any error -> Tier 0 action
  2. every action is clamped to the legal set before it is sent
  3. hard deadline / emergency mode -> Tier 0 without calling the brain
The loop never lets an exception escape; it exits cleanly on EOF or ENDMATCH.
"""
from __future__ import annotations

import os
import sys

if __package__ in (None, ""):  # allow `python bot/main.py` as well as `-m bot.main`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib
from typing import Optional, TextIO

from bot import log as botlog
from bot.actions import Action, LegalActions, clamp, safe_action
from bot.brains.base import Brain
from bot.protocol import ActRequest, MatchEnd, MatchInfo, Message, ProtocolError
from bot.protocols import ADAPTERS, get_adapter
from bot.state import GameState
from bot.timing import DeadlineExceeded, Stopwatch, TimeManager, hard_deadline

# Brain registry: name -> "module:Class", imported lazily so startup stays fast.
BRAINS = {
    "tier0": "bot.brains.tier0:Tier0Brain",
    "tier1": "bot.brains.tier1:Tier1Brain",
    "tier2": "bot.brains.tier2:Tier2Brain",
}
DEFAULT_BRAIN = "tier2"


def load_brain(name: str) -> Brain:
    module, _, cls = BRAINS[name].partition(":")
    return getattr(importlib.import_module(module), cls)()


class Bot:
    def __init__(self, brain: Brain, out: Optional[TextIO], timer: Optional[TimeManager] = None,
                 adapter=None) -> None:
        self.brain = brain
        self.out = out
        self.adapter = adapter or get_adapter()
        self.timer = timer or TimeManager()
        self.state = GameState()
        # Counters, handy for tests and the end-of-match stderr summary.
        self.brain_errors = 0
        self.deadline_hits = 0
        self.emergency_decisions = 0
        self.bad_lines = 0

    # ---- main loop
    def run(self, stream: TextIO) -> int:
        while True:
            try:
                line = stream.readline()
            except Exception as e:  # e.g. decode error on a broken stream
                botlog.warn(f"read failed: {e!r}")
                self.bad_lines += 1
                continue
            if not line:
                break  # EOF
            try:
                if not self.handle_line(line):
                    break
            except BrokenPipeError:
                break
            except Exception as e:  # last-resort guard: never crash on one line
                botlog.warn(f"unhandled error on line {line.strip()!r}: {e!r}")
        botlog.log(f"done: hands={self.state.hands_played} bankroll={self.state.bankroll} "
                   f"brain_errors={self.brain_errors} deadlines={self.deadline_hits} "
                   f"emergency={self.emergency_decisions} bad_lines={self.bad_lines}")
        return 0

    def handle_line(self, line: str) -> bool:
        """Process one engine line. Returns False when the match is over."""
        try:
            msg = self.adapter.parse_line(line)
        except ProtocolError as e:
            self.bad_lines += 1
            botlog.warn(f"malformed line {line.strip()!r}: {e}")
            return True
        if msg is None:
            return True  # blank or unknown: ignore
        action = self.on_message(msg)
        if action is not None and self.out is not None:
            self.out.write(self.adapter.encode_action(action) + "\n")
            self.out.flush()
        return not isinstance(msg, MatchEnd)

    def on_message(self, msg: Message) -> Optional[Action]:
        """Apply one neutral message; returns our (legal) action if it was an ACT.
        The lab's in-process player calls this directly, skipping the text format."""
        self.state.apply(msg)
        action = None
        if isinstance(msg, MatchInfo):
            self.timer.configure(msg.timebank, msg.hands)
        elif isinstance(msg, ActRequest):
            watch = Stopwatch()
            self.timer.observe_timeleft(msg.timeleft)
            action = clamp(self.choose(msg.legal), msg.legal)
            self.state.record_my_action(action)
            self.timer.add_used(watch.elapsed())
        try:
            self.brain.observe(self.state, msg)
        except Exception as e:
            self.brain_errors += 1
            botlog.warn(f"brain.observe failed: {e!r}")
        return action

    def choose(self, legal: LegalActions) -> Action:
        """Ask the brain, with Tier 0 fallback on emergency, error or deadline."""
        if self.timer.emergency():
            self.emergency_decisions += 1
            return safe_action(legal)
        budget = self.timer.budget(self.state.hands_remaining)
        try:
            with hard_deadline(self.timer.hard_limit(budget)):
                return self.brain.decide(self.state, legal, budget)
        except DeadlineExceeded:
            self.deadline_hits += 1
            botlog.warn(f"brain exceeded hard deadline (budget {budget * 1000:.1f} ms)")
        except Exception as e:
            self.brain_errors += 1
            botlog.warn(f"brain error: {e!r}")
        return safe_action(legal)


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--verbose" in args:
        botlog.VERBOSE = True
    protocol = None
    if "--protocol" in args:
        i = args.index("--protocol")
        if i + 1 < len(args) and args[i + 1] in ADAPTERS:
            protocol = args[i + 1]
        else:
            botlog.warn("unknown protocol, using the default")
    name = DEFAULT_BRAIN
    if "--brain" in args:
        i = args.index("--brain")
        if i + 1 < len(args) and args[i + 1] in BRAINS:
            name = args[i + 1]
        else:
            botlog.warn(f"unknown brain, using {DEFAULT_BRAIN}")

    # Keep the real stdout for actions only; any stray print() now lands on stderr.
    out = sys.stdout
    sys.stdout = sys.stderr
    try:
        sys.stdin.reconfigure(errors="replace")  # garbage bytes must not raise
    except Exception:
        pass

    try:
        brain = load_brain(name)
    except Exception as e:
        botlog.warn(f"could not load brain {name!r} ({e!r}); using tier0")
        brain = load_brain("tier0")
    try:
        adapter = get_adapter(protocol)
    except Exception as e:
        botlog.warn(f"could not load protocol {protocol!r} ({e!r}); using placeholder")
        adapter = get_adapter("placeholder")
    try:
        return Bot(brain, out, adapter=adapter).run(sys.stdin)
    except BaseException as e:  # including KeyboardInterrupt / stray DeadlineExceeded
        botlog.warn(f"fatal: {e!r}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
