"""Game state for one hand, plus the event log that defines who saw what.

Everything a player can learn is an `Event` with a `visible` field: ALL (public) or the
index of the one player who sees it. Observations (bot/game/observation.py) are built only
from events, so hidden-information correctness can be tested by checking the events.

Players are indexed by role: 0 = small blind / button, 1 = big blind (heads-up).
"""
from __future__ import annotations

from typing import Any, NamedTuple, Optional

ALL = -1

# Event kinds that are allowed to show cards another player holds privately (or undealt
# cards, for peeks). Their correctness is tested per step; every other kind is audited.
REVEAL_KINDS = frozenset({"showdown", "expose", "peek", "reveal"})
# Kinds that carry card information to players (sent as INFO messages by the engine).
INFO_KINDS = frozenset({"expose", "peek", "reveal", "burn", "offer"})


class Event(NamedTuple):
    kind: str          # "hole", "board", "action", "special", "blinds", "showdown", "end", ...
    player: int        # actor / owner (-1 if none)
    data: dict         # payload; card lists live under "cards"
    visible: int = ALL


class VisibilityError(AssertionError):
    """A step emitted an event that shows a player cards they must not see."""


class GameState:
    __slots__ = ("rules", "deck", "hole", "board", "start", "stack", "bet", "total", "folded",
                 "street", "rounds_done", "last_raise", "raises", "pc", "entered", "step_state",
                 "events", "record", "audit", "done", "deltas", "showdown", "hand_id", "extra",
                 "muck", "rng", "level")

    def __init__(self, rules, deck: list[int], stacks: list[int], hand_id: int = 0,
                 record: bool = True, audit: bool = False, level=None) -> None:
        self.rules = rules
        # (sb, bb, ante, straddle) for this hand; None = the steps' own defaults
        self.level = level if level is not None else getattr(rules, "level_at", lambda h: None)(hand_id)
        self.deck = list(deck)              # undealt cards, dealt from the front
        n = len(stacks)
        self.hole: list[list[int]] = [[] for _ in range(n)]
        self.board: list[int] = []
        self.muck: list[int] = []           # discarded / burned / unchosen cards
        self.start = list(stacks)
        self.stack = list(stacks)
        self.bet = [0] * n                  # this betting round
        self.total = [0] * n                # whole hand
        self.folded: Optional[int] = None
        self.street = 0                     # number of board deals so far (0 = preflop)
        self.rounds_done = 0                # betting rounds finished
        self.last_raise = 0
        self.raises = 0
        self.pc = 0                         # index of the current step in the program
        self.entered = False                # has the current step's begin() run?
        self.step_state: Any = None         # per-step scratch (e.g. betting: who still acts)
        self.events: list[Event] = []
        self.record = record                # False in fast simulations: no event log
        self.audit = audit                  # True in tests: check every event's visibility
        self.done = False
        self.deltas: Optional[list[int]] = None
        self.showdown = False
        self.hand_id = hand_id
        self.extra: dict = {}               # room for plugin data (bounties, bids, ...)
        self.rng = None                     # set by the runner; steps call random()

    # ---- basics
    @property
    def n_players(self) -> int:
        return len(self.stack)

    @property
    def pot(self) -> int:
        return sum(self.total)

    def to_call(self, p: int) -> int:
        return max(self.bet) - self.bet[p]

    def deal(self, n: int) -> list[int]:
        if n > len(self.deck):
            raise ValueError(f"deck exhausted: need {n}, have {len(self.deck)}")
        cards, self.deck = self.deck[:n], self.deck[n:]
        return cards

    def random(self):
        """The hand's random generator (numpy-like: .random(), .integers(...))."""
        if self.rng is None:
            import numpy as np
            self.rng = np.random.default_rng(self.hand_id)
        return self.rng

    def pay_cost(self, p: int, amount: int) -> int:
        """A non-betting payment into the pot (draw / peek / swap costs): counts toward
        the pot but not toward this round's bets."""
        amount = max(0, min(amount, self.stack[p]))
        self.stack[p] -= amount
        self.total[p] += amount
        return amount

    def pay(self, p: int, amount: int) -> int:
        """Move up to `amount` chips from p's stack into the pot; returns what was paid."""
        amount = max(0, min(amount, self.stack[p]))
        self.stack[p] -= amount
        self.bet[p] += amount
        self.total[p] += amount
        return amount

    # ---- events
    def emit(self, kind: str, player: int = -1, visible: int = ALL, **data) -> None:
        if self.audit:
            self._check_visibility(kind, visible, data)
        if self.record:
            self.events.append(Event(kind, player, data, visible))

    def _check_visibility(self, kind: str, visible: int, data: dict) -> None:
        if kind in REVEAL_KINDS:
            return
        for c in data.get("cards", ()):
            if c in self.deck:
                raise VisibilityError(f"{kind}: undealt card {c} shown")
            for q in range(self.n_players):
                if c in self.hole[q] and visible != q:
                    raise VisibilityError(f"{kind}: player {q}'s hole card {c} shown to "
                                          f"{'everyone' if visible == ALL else visible}")

    # ---- simulation support
    def copy(self, record: bool = False) -> "GameState":
        """Independent copy for simulations (event log dropped unless record=True)."""
        g = GameState.__new__(GameState)
        g.rules = self.rules
        g.deck = list(self.deck)
        g.hole = [list(h) for h in self.hole]
        g.board = list(self.board)
        g.muck = list(self.muck)
        g.rng = self.rng
        g.level = self.level
        g.start, g.stack = list(self.start), list(self.stack)
        g.bet, g.total = list(self.bet), list(self.total)
        g.folded, g.street, g.rounds_done = self.folded, self.street, self.rounds_done
        g.last_raise, g.raises = self.last_raise, self.raises
        g.pc, g.entered = self.pc, self.entered
        ss = self.step_state
        g.step_state = ss.copy() if hasattr(ss, "copy") else ss
        g.events = list(self.events) if record else []
        g.record, g.audit = record, False
        g.done, g.showdown, g.hand_id = self.done, self.showdown, self.hand_id
        g.deltas = list(self.deltas) if self.deltas is not None else None
        g.extra = {k: (v.copy() if hasattr(v, "copy") else v) for k, v in self.extra.items()}
        return g
