"""Round-trip conformance for any wire adapter.

Play seeded hands in the lab engine with two recording in-process players. Each records the
neutral messages it receives, the bot-side GameState at every ActRequest and the action it
chose. Then, per seat, the recorded stream goes through the adapter's engine side
(encode_message), through a fresh bot side (parse_line) and into a fresh GameState; at every
ActRequest the decoded state must equal the recorded one. Replies must also survive
encode_action -> parse_action. A mismatch is reported with the messages and lines around it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from bot.actions import Action, LegalActions
from bot.cards import format_cards
from bot.protocol import ActRequest, Message
from bot.protocols import get_adapter
from bot.protocols.base import as_lines, as_messages as as_msgs
from bot.state import GameState
from kit.scenario import load_spec
from lab.engine import play_match


class RoundTripError(AssertionError):
    pass


def snapshot(st: GameState) -> dict[str, Any]:
    """The part of the bot-side state a decision can depend on, as comparable plain data."""
    h = st.hand
    assert h is not None
    return {
        "hand_id": h.hand_id, "seat": h.seat, "hole": h.hole, "board": h.board,
        "street": h.street, "pot": h.pot, "tocall": h.tocall, "my_bet": h.my_bet,
        "opp_bet": h.opp_bet, "my_stack": h.my_stack, "opp_stack": h.opp_stack,
        "start_stack": h.start_stack, "opp_start_stack": h.opp_start_stack,
        "history": [(r.street, r.actor, r.action.kind, r.action.amount, r.action.choice)
                    for r in h.history],
        "info": [(i.kind, i.who, i.cards, i.value) for i in h.info],
        "dead": sorted(h.dead_cards),
    }


def hide_opponent_choice(snap: dict) -> dict:
    """For formats that never say WHICH hidden card the opponent discarded: forget the index
    of the opponent's special actions (the revealed card itself is still compared)."""
    out = dict(snap)
    out["history"] = [(s, a, k, amt, None if (a == "opp" and k == "S") else ch)
                      for s, a, k, amt, ch in snap["history"]]
    return out


class Recorder:
    """An in-process player: random legal moves, and a log of everything it was sent."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.state = GameState()
        self.events: list[tuple] = []          # ("msg", m) | ("act", req, action, snapshot)
        self.name = "recorder"

    def notify(self, msg: Message) -> None:
        self.state.apply(msg)
        self.events.append(("msg", msg))

    def act(self, req: ActRequest) -> Action:
        self.state.apply(req)
        action = self.pick(req.legal)
        self.events.append(("act", req, action, snapshot(self.state)))
        self.state.record_my_action(action)
        return action

    def close(self) -> None:
        pass

    def pick(self, legal: LegalActions) -> Action:
        r, rng = self.rng.random(), self.rng
        if legal.can_special:
            sp = legal.special
            return Action.special(str(rng.randint(sp.lo, sp.hi)) if sp.is_range
                                  else rng.choice(sp.choices))
        if legal.can_raise and r < 0.35:
            if rng.random() < 0.25:
                return Action.raise_to(legal.raise_max)           # shove: all-ins and showdowns
            return Action.raise_to(legal.nearest_raise(rng.randint(legal.raise_min,
                                                                    legal.raise_max)))
        if legal.fold and r > 0.9:
            return Action.fold()
        if legal.call:
            return Action.call()
        if legal.check:
            return Action.check()
        return Action.fold()


@dataclass
class RoundTripReport:
    hands: int
    requests: int = 0
    seats: list[int] = field(default_factory=lambda: [0, 0])


def record_match(spec: str, hands: int, seed: int) -> list[Recorder]:
    players = [Recorder(seed * 2 + 1), Recorder(seed * 2 + 2)]
    play_match(players, load_spec(spec), seed, hands, audit=True)
    return players


def check_round_trip(adapter: str, spec: str = "holdem_nl", hands: int = 50, seed: int = 0
                     ) -> RoundTripReport:
    report = RoundTripReport(hands)
    for seat, rec in enumerate(record_match(spec, hands, seed)):
        engine, bot = get_adapter(adapter), get_adapter(adapter)
        st, k = GameState(), 0
        context: list[str] = []
        for ev in rec.events:
            msg = ev[1]
            lines = as_lines(engine.encode_message(msg))
            context.append(f"  engine msg {msg!r}\n    -> lines {lines!r}")
            for line in lines:
                for m in as_msgs(bot.parse_line(line)):
                    st.apply(m)
                    if not isinstance(m, ActRequest):
                        continue
                    _, req, action, want = ev
                    got = snapshot(st)
                    if bot.hides_opponent_choice:
                        want, got = hide_opponent_choice(want), hide_opponent_choice(got)
                    bad = [key for key in want if want[key] != got[key]]
                    if m.legal != req.legal:
                        bad.append("legal")
                    if bad:
                        raise RoundTripError(_explain(adapter, seat, k, bad, want, got, m, req,
                                                      context))
                    reply = bot.encode_action(action)
                    back = engine.parse_action(reply)
                    if back != action:
                        raise RoundTripError(f"{adapter} seat {seat} request {k}: reply "
                                             f"{action!r} -> {reply!r} -> {back!r}")
                    st.record_my_action(action)
                    k += 1
        if k != sum(1 for e in rec.events if e[0] == "act"):
            raise RoundTripError(f"{adapter} seat {seat}: {k} decoded requests, "
                                 f"{sum(1 for e in rec.events if e[0] == 'act')} sent")
        report.requests += k
        report.seats[seat] = k
    return report


def _explain(adapter, seat, k, bad, want, got, m, req, context) -> str:
    diffs = "\n".join(f"  {key}: sent {want.get(key)!r}, decoded {got.get(key)!r}"
                      for key in bad if key != "legal")
    if "legal" in bad:
        diffs += f"\n  legal: sent {req.legal!r}, decoded {m.legal!r}"
    tail = "\n".join(context[-8:])
    return (f"{adapter}, seat {seat}, request {k}: state differs on {bad}\n{diffs}\n"
            f"last messages:\n{tail}\nhole {format_cards(want['hole'])}")
