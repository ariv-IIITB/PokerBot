"""Shadow tier3x inside the teammate's final CFR bot (bundled as botsrc.shadow by build_variant.py).

The shadow is the user's whole tier3x bot (the bot/ and variant/ packages, bundled into _SOURCES). It reads every
engine line through its own pokerbots adapter and keeps its own game state, opponent model and type posterior, but
it never answers an action request itself: the final bot replies, and the shadow is told what we did, exactly as if
tier3x had chosen it. What it can give the final bot (features, CONFIG "shadow" = comma list):
  discard   tier3x's own PIMC discard (discard(line, hole))
  range     tier3x's opponent river range, Opponent.range_weights with its river model (river_range())
  types     X2 type-posterior confidence of a style family, as tier3x's typefamily_lambda (family_lambda(name))

Two ways to feed it (both kept): the first shadisc build feeds every line after our reply (feed + acted); the
later builds feed each request line BEFORE the final bot decides (so the range is current), via pre(line), and
tell it our reply afterwards via acted(reply), discards included.

Never fatal: any error turns the shadow off for the rest of the leg (its state may no longer match the hand), and
the final bot plays without it from then on."""
import json
import time

import numpy as np

from bot.actions import SPECIAL, Action, clamp, is_legal
from bot.main import Bot, load_brain
from bot.protocol import ActRequest
from bot.protocols import get_adapter
from bot.protocols.base import as_messages

CURRENT = None                     # the running Shadow (set by the final bot), for exploit.py and policy.py

# tier3x's EXPLOIT_DEFAULTS for the type-family ramp (bot/brains/exploit.py typefamily_lambda)
FAM_MIN, FAM_FULL, FAM_MIN_OBS = 0.60, 0.85, 20


def _now_ms():
    return time.perf_counter() * 1000.0


class Shadow:
    def __init__(self, features=("discard",)):
        t0 = _now_ms()
        self.features = frozenset(features)
        self.bot = Bot(load_brain("tier3x"), None, adapter=get_adapter("pokerbots"))
        self.dead = None                  # the error that turned the shadow off, if any
        self.pending = None               # the request the final bot is answering
        self.discards = 0
        self.discard_ms = 0.0
        self.feed_ms = 0.0
        self.ranges = 0
        self.range_ms = 0.0
        self.range_none = 0
        self.fam_calls = 0
        self.fam_max = {}
        self._map = None
        self.startup_ms = _now_ms() - t0

    def _die(self, where, e):
        if self.dead is None:
            self.dead = f"{where}: {type(e).__name__}: {e}"

    @property
    def alive(self):
        return self.dead is None

    # ------------------------------------------------------------ feeding
    def feed(self, line):
        """Any engine line (a request too: state only, no decision; the reply comes through acted)."""
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

    pre = feed

    def acted(self, reply):
        """The final bot's reply to the pending request (an action or a discard): record it as ours."""
        if self.dead is not None:
            return
        t0 = _now_ms()
        try:
            m, self.pending = self.pending, None
            if m is None:
                raise ValueError("a reply without a pending request")
            b = self.bot
            if reply.get("type") == "discard":
                hole = b.adapter.hole
                cards = [json.loads(b.adapter.encode_action(Action.special(str(i))))["card"]
                         for i in range(len(hole))]
                a = Action.special(str(cards.index(reply["card"])))
            else:
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
            if a.kind != SPECIAL and not m.legal.can_special:
                b.adapter.encode_action(a)        # keeps the adapter's record of what we sent
            b.state.record_my_action(a)
            b.brain.observe(b.state, m)
        except Exception as e:
            self._die("acted", e)
        self.feed_ms += _now_ms() - t0

    # ------------------------------------------------------------ discard
    def discard(self, line, hole):
        """tier3x's discard card (wire string) for this discard_request line, or None. (First build: the
        discard_request line is fed here, and tier3x's choice is recorded as ours.)"""
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

    def discard_pending(self, hole):
        """Later builds: the discard request was fed by pre(); tier3x decides now (not yet recorded: the final
        bot's actual reply comes through acted)."""
        if self.dead is not None or self.pending is None:
            return None
        t0 = _now_ms()
        card = None
        try:
            b = self.bot
            m = self.pending
            a = b.choose(m.legal)
            if not is_legal(a, m.legal):
                raise ValueError(f"illegal shadow discard {a!r}")
            card = json.loads(b.adapter.encode_action(a))["card"]
            if card not in hole:
                raise ValueError(f"shadow discard {card!r} not in {hole!r}")
            self.discards += 1
        except Exception as e:
            self._die("discard", e)
            card = None
        self.discard_ms += _now_ms() - t0
        return card

    # ------------------------------------------------------------ range
    def _card_map(self):
        if self._map is None:
            from bot.cards import format_card
            from shared import cards as FC
            m = np.array([FC.parse_card(format_card(u)) for u in range(52)], dtype=np.int64)
            if len(set(m.tolist())) != 52:
                raise ValueError("card map is not a bijection")
            self._map = m
        return self._map

    def river_range(self):
        """float64[1326] in the final bot's pair index: tier3x's opponent range at this river decision
        (Opponent.range_weights over every pair of unseen cards, with tier3x's river model), or None."""
        if self.dead is not None:
            return None
        t0 = _now_ms()
        out = None
        try:
            b = self.bot
            brain = b.brain
            s = brain.situation(b.state)
            h, rec = s.hand, s.rec
            if h is None or rec is None or len(h.hole) != 2 or len(h.board) != 5 \
                    or len(rec.state.hole[rec.me]) != 2:
                self.range_none += 1
                return None
            pool = np.array(sorted(rec.pool), dtype=np.int64)
            i, j = np.triu_indices(len(pool), 1)
            opp_cards = np.stack([pool[i], pool[j]], axis=1)
            w = np.asarray(brain.opponent.range_weights(rec, opp_cards, brain.rng,
                                                        brain._river_opp_model(brain.p)), dtype=np.float64)
            from shared import cards as FC
            m = self._card_map()
            idx = FC.idx2_array(m[opp_cards[:, 0]], m[opp_cards[:, 1]])
            out = np.zeros(1326)
            out[idx] = w
            if not (np.isfinite(out).all() and (out >= 0).all() and out.sum() > 0):
                self.range_none += 1
                out = None
            else:
                self.ranges += 1
        except Exception as e:
            self._die("range", e)
            out = None
        finally:
            self.range_ms += _now_ms() - t0
        return out

    # ------------------------------------------------------------ types
    def family_lambda(self, family):
        """0..1: tier3x's type-posterior confidence that the opponent is of this style family."""
        if self.dead is not None:
            return 0.0
        try:
            types = self.bot.brain.opponent.types
            if types is None or types.n == 0:
                return 0.0
            mass = types.families().get(family, 0.0)
            lam = max(0.0, min(1.0, (mass - FAM_MIN) / (FAM_FULL - FAM_MIN)))
            lam *= min(1.0, types.n / float(FAM_MIN_OBS))
            self.fam_calls += 1
            if lam > self.fam_max.get(family, 0.0):
                self.fam_max[family] = round(lam, 3)
            return lam
        except Exception as e:
            self._die("types", e)
            return 0.0

    def summary(self):
        b = self.bot
        top = None
        try:
            t = b.brain.opponent.types
            top = t.top() if t is not None else None
        except Exception:
            pass
        return (f"shadow tier3x: features {sorted(self.features)}, start-up {self.startup_ms:.0f} ms, "
                f"{self.discards} discards in {self.discard_ms:.0f} ms, {self.ranges} ranges in {self.range_ms:.0f} ms "
                f"({self.range_none} none), family calls {self.fam_calls} max {self.fam_max}, top type {top}, "
                f"feed {self.feed_ms:.0f} ms, brain errors {b.brain_errors}, deadlines {b.deadline_hits}, "
                f"emergency {b.emergency_decisions}, {'OFF since ' + self.dead if self.dead else 'on to the end'}")
