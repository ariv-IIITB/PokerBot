"""Shadow tier3x inside the teammate's final CFR bot (bundled as botsrc.shadow by build_variant.py, arm shadisc).

The shadow is the user's whole tier3x bot (the bot/ package, bundled into _SOURCES). It reads every engine line
through its own pokerbots adapter and keeps its own game state and opponent model, but it never answers an
action request: after the final bot has replied, the shadow is told what we did, exactly as if tier3x had chosen
it. It answers only the discard request, with tier3x's own PIMC discard.

Never fatal: any error turns the shadow off for the rest of the leg (its state may no longer match the hand),
and the final bot plays its own discard from then on."""
import json
import time

from bot.actions import Action, clamp, is_legal
from bot.main import Bot, load_brain
from bot.protocol import ActRequest
from bot.protocols import get_adapter
from bot.protocols.base import as_messages


def _now_ms():
    return time.perf_counter() * 1000.0


class Shadow:
    def __init__(self):
        t0 = _now_ms()
        self.bot = Bot(load_brain("tier3x"), None, adapter=get_adapter("pokerbots"))
        self.dead = None                  # the error that turned the shadow off, if any
        self.pending = None               # the action request the final bot is answering
        self.discards = 0
        self.discard_ms = 0.0
        self.feed_ms = 0.0
        self.startup_ms = _now_ms() - t0

    def _die(self, where, e):
        if self.dead is None:
            self.dead = f"{where}: {type(e).__name__}: {e}"

    def feed(self, line):
        """Any engine line except a discard request. For an action request: state only, no decision."""
        if self.dead is not None:
            return
        t0 = _now_ms()
        try:
            b = self.bot
            for m in as_messages(b.adapter.parse_line(line)) or ():
                if isinstance(m, ActRequest):
                    b.state.apply(m)
                    b.timer.observe_timeleft(m.timeleft)
                    self.pending = m
                else:
                    b.on_message(m)
        except Exception as e:
            self._die("feed", e)
        self.feed_ms += _now_ms() - t0

    def acted(self, reply):
        """The final bot's reply to the pending action request: record it as our own action."""
        if self.dead is not None:
            return
        t0 = _now_ms()
        try:
            m, self.pending = self.pending, None
            if m is None:
                raise ValueError("a reply without a pending request")
            name = reply.get("action")
            if name == "raise":
                a = Action.raise_to(int(reply["amount"]))
            elif name == "fold":
                a = Action.fold()
            elif name == "check":
                a = Action.check()
            elif name == "call":
                a = Action.call()
            else:
                raise ValueError(f"unknown reply {reply!r}")
            if not is_legal(a, m.legal):
                a = clamp(a, m.legal)
            b = self.bot
            b.adapter.encode_action(a)            # keeps the adapter's record of what we sent
            b.state.record_my_action(a)
            b.brain.observe(b.state, m)
        except Exception as e:
            self._die("acted", e)
        self.feed_ms += _now_ms() - t0

    def discard(self, line, hole):
        """tier3x's discard card (wire string) for this discard_request line, or None."""
        if self.dead is not None:
            return None
        t0 = _now_ms()
        card = None
        try:
            b = self.bot
            action = None
            for m in as_messages(b.adapter.parse_line(line)) or ():
                a = b.on_message(m)                # the ActRequest: tier3x decides (validated, recorded)
                if a is not None:
                    action = a
            if action is None:
                raise ValueError("no discard decision")
            card = json.loads(b.adapter.encode_action(action))["card"]
            if card not in hole:
                raise ValueError(f"shadow discard {card!r} not in {hole!r}")
            self.discards += 1
        except Exception as e:
            self._die("discard", e)
            card = None
        self.discard_ms += _now_ms() - t0
        return card

    def summary(self):
        b = self.bot
        return (f"shadow tier3x: start-up {self.startup_ms:.0f} ms, {self.discards} discards in "
                f"{self.discard_ms:.0f} ms, feed {self.feed_ms:.0f} ms, brain errors {b.brain_errors}, "
                f"deadlines {b.deadline_hits}, emergency {b.emergency_decisions}, "
                f"{'OFF since ' + self.dead if self.dead else 'on to the end'}")
