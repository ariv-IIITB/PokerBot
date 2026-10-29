"""Per-spot opponent statistics with a population prior, a sample gate and a capped shift.

Every spot is a rate (hits / n) seen from our side, started at what LLM-built bots usually do
(the prior, worth `strength` observations). Play only moves away from its base when a spot has
at least `gate` real observations, and never by more than `cap` (15 points) in either direction,
so a short run of luck cannot swing the strategy:

    shift = 0                                   while n < gate
          = clip(mean - prior, -cap, +cap)      afterwards       (mean = (hits + prior*strength) / (n + strength))

Spots (phase E; phase G adds the rest):
  bluff_index    of the opponent's turn/river bets that we saw at showdown, the share whose hand
                 was weak (below `weak_below` of all two-card hands on that board). Low = a
                 value-heavy bettor: fold bluff-catchers to big bets.
  fold_flop/turn/river   the opponent folded to our bet or raise, per street.
  fold_small/mid/big     the same by size of our bet (fraction of the pot: < 0.5, < 0.9, bigger).

The module has no card logic beyond `hand_percentile`; feeding it is the brain's job
(`note_raise` when we bet, `update` for every message).
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional, Sequence

import numpy as np

from bot.actions import FOLD, RAISE
from bot.protocol import HandEnd, HandStart, Message, OppAction, Showdown
from bot.state import ME, GameState

# What a typical LLM-built bot does, learned from the Hold'em pool (docs/reports/OPPS_ANALYSIS.md):
# bets mostly for value, over-calls, folds a bit more to big bets.
POPULATION = {"bluff_index": 0.15,
              "fold_flop": 0.35, "fold_turn": 0.40, "fold_river": 0.45,
              "fold_small": 0.25, "fold_mid": 0.35, "fold_big": 0.45}
STREET_SPOT = {1: "fold_flop", 2: "fold_turn", 3: "fold_river"}
SIZE_EDGES = (0.5, 0.9)                 # pot fractions: small < 0.5 <= mid < 0.9 <= big
STRENGTH = 15.0                         # prior worth this many observations
GATE = 20                               # observations before a spot may move play
CAP = 0.15                              # largest move from the prior, in probability


@dataclass
class Spot:
    prior: float
    strength: float = STRENGTH
    hits: int = 0
    n: int = 0

    def add(self, hit: bool) -> None:
        self.n += 1
        self.hits += int(hit)

    def mean(self) -> float:
        return (self.hits + self.prior * self.strength) / (self.n + self.strength)

    def shift(self, gate: int = GATE, cap: float = CAP) -> float:
        """How far play may move from the prior: 0 below the gate, then capped."""
        if self.n < gate:
            return 0.0
        return float(min(cap, max(-cap, self.mean() - self.prior)))


def size_bucket(frac: float) -> str:
    return "fold_small" if frac < SIZE_EDGES[0] else ("fold_mid" if frac < SIZE_EDGES[1] else "fold_big")


def hand_percentile(evaluator, hole: Sequence[int], board: Sequence[int], deck: Sequence[int],
                    dead: Sequence[int] = ()) -> float:
    """Where `hole` ranks among every two-card hand that could be held on this (full) board:
    the share of the other hands it beats, ties counting half. 1.0 = the nuts."""
    seen = set(hole) | set(board) | set(dead)
    rest = [c for c in deck if c not in seen]
    combos = np.array(list(combinations(rest, 2)), dtype=np.intp)
    board_np = np.array(board, dtype=np.intp)
    mine = int(evaluator.evaluate(list(hole), list(board)))
    theirs = evaluator.evaluate_batch(combos, board_np)
    return float(((theirs < mine).sum() + 0.5 * (theirs == mine).sum()) / len(theirs))


class OppStats:
    def __init__(self, priors: Optional[dict] = None, strength: float = STRENGTH,
                 gate: int = GATE, cap: float = CAP, weak_below: float = 0.5) -> None:
        pri = dict(POPULATION)
        pri.update(priors or {})
        self.spots = {k: Spot(v, strength) for k, v in pri.items()}
        self.gate, self.cap, self.weak_below = gate, cap, weak_below
        self._pending: Optional[tuple[int, str]] = None     # (street, size bucket) of our last raise

    # ---- reading
    def mean(self, spot: str) -> float:
        return self.spots[spot].mean()

    def shift(self, spot: str) -> float:
        return self.spots[spot].shift(self.gate, self.cap)

    def bluff_index(self) -> float:
        """The opponent's bluff index as play should use it: the prior moved by the gated,
        capped shift."""
        s = self.spots["bluff_index"]
        return s.prior + s.shift(self.gate, self.cap)

    def fold_prob(self, frac: float, street: int) -> float:
        """P(opponent folds to our bet of `frac` x pot on `street`), prior plus capped shifts."""
        b = self.spots[size_bucket(frac)]
        move = self.shift(size_bucket(frac)) + 0.5 * self.shift(STREET_SPOT.get(street, "fold_river"))
        move = max(-self.cap, min(self.cap, move))
        return float(min(0.95, max(0.02, b.prior + move)))

    # ---- feeding
    def note_raise(self, street: int, frac: float) -> None:
        """We bet or raised `frac` x the pot on `street`; the opponent's next action answers it."""
        self._pending = (street, size_bucket(frac))

    def update(self, state: GameState, msg: Message, hand_percentile_of=None) -> None:
        """Feed one neutral message. `hand_percentile_of(oppcards, board)` ranks a shown hand
        (the brain supplies it: it owns the evaluator and the deck)."""
        h = state.hand
        if isinstance(msg, HandStart):
            self._pending = None
        elif isinstance(msg, OppAction):
            if self._pending is not None:
                street, bucket = self._pending
                self._pending = None
                folded = msg.action.kind == FOLD
                self.spots[bucket].add(folded)
                if street in STREET_SPOT:
                    self.spots[STREET_SPOT[street]].add(folded)
        elif isinstance(msg, Showdown) and h is not None and hand_percentile_of is not None:
            bets = [r for r in h.history if r.actor != ME and r.street >= 2 and r.action.kind == RAISE]
            if bets and len(h.board) >= 5 and len(msg.oppcards) >= 2:
                try:
                    pct = hand_percentile_of(msg.oppcards, h.board)
                except Exception:
                    return
                self.spots["bluff_index"].add(pct < self.weak_below)
        elif isinstance(msg, HandEnd):
            self._pending = None
