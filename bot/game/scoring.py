"""Showdown scoring: turns hands into pot shares.

A Scorer has one or more components:
  high only              the best high hand takes the pot
  low only (2-7 / A-5)   the best low hand takes the pot
  hi-lo                  half to the best high, half to the best qualifying low; if no
                         low qualifies, the high takes everything
  several boards         the pot is split evenly per board, and each board's share is
                         decided as above using that board
`shares(holes, boards)` returns each player's fraction of the pot (ties split equally).
`evaluate` / `evaluate_batch` give the primary component's value (used by equity code).

Custom scoring functions (taxonomy D: "sum of ranks", "highest heart", ...) register in
SCORES and are selected with evaluation.kind = "score", evaluation.score = <name>.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

import numpy as np

from bot.evaluator import NOT_QUALIFIED

# name -> fn(hole, board, deck) -> comparable int (higher wins)
SCORES: dict[str, Callable] = {}


def register_score(name: str):
    def deco(fn):
        SCORES[name] = fn
        return fn
    return deco


@register_score("hole_rank_sum")
def hole_rank_sum(hole, board, deck) -> int:
    """Sum of the rank positions of the player's hole cards (board ignored)."""
    pos = deck.pos_high
    return int(sum(int(pos[c]) for c in hole))


@register_score("best_heart")
def best_heart(hole, board, deck) -> int:
    """Highest heart among hole + board cards; -1 without a heart."""
    hearts = [int(deck.pos_high[c]) for c in list(hole) + list(board) if deck.suit[c] == 2]
    return max(hearts) if hearts else -1


class CustomEvaluator:
    """Wraps a registered scoring function with the evaluator interface."""

    def __init__(self, fn: Callable, deck) -> None:
        self.fn, self.deck = fn, deck

    def evaluate(self, hole, board) -> int:
        return int(self.fn(list(hole), list(board), self.deck))

    def evaluate_batch(self, hole, board) -> np.ndarray:
        hole = np.atleast_2d(np.asarray(hole))
        board = np.asarray(board)
        board = board.reshape(1, -1) if board.ndim == 1 else board
        n = max(hole.shape[0], board.shape[0])
        hole = np.broadcast_to(hole, (n, hole.shape[1]))
        board = np.broadcast_to(board, (n, board.shape[1]))
        return np.array([self.evaluate(h, b) for h, b in zip(hole.tolist(), board.tolist())],
                        dtype=np.int64)


def _winners(values: Sequence[int]) -> list[int]:
    best = max(values)
    return [p for p, v in enumerate(values) if v == best]


class Scorer:
    def __init__(self, high=None, low=None) -> None:
        """high and/or low evaluators (hi-lo when both are given)."""
        if high is None and low is None:
            raise ValueError("a scorer needs a high or a low evaluator")
        self.high, self.low = high, low
        self.primary = high if high is not None else low
        self.hilo = high is not None and low is not None

    # ---- primary component (equity, legacy callers)
    def evaluate(self, hole, board) -> int:
        return self.primary.evaluate(hole, board)

    def evaluate_batch(self, hole, board) -> np.ndarray:
        return self.primary.evaluate_batch(hole, board)

    def warm_up(self) -> None:
        for ev in (self.high, self.low):
            if ev is not None and hasattr(ev, "warm_up"):
                ev.warm_up()

    # ---- pot shares
    def board_shares(self, holes: Sequence[Sequence[int]], board: Sequence[int]) -> list[float]:
        n = len(holes)
        out = [0.0] * n
        if self.hilo:
            hi = [self.high.evaluate(h, board) for h in holes]
            lo = [self.low.evaluate(h, board) for h in holes]
            parts = [(hi, 0.5), (lo, 0.5)] if max(lo) > NOT_QUALIFIED else [(hi, 1.0)]
        else:
            ev = self.primary
            vals = [ev.evaluate(h, board) for h in holes]
            if max(vals) <= NOT_QUALIFIED and self.low is not None:
                return [1.0 / n] * n          # nobody qualifies for a low-only pot: split
            parts = [(vals, 1.0)]
        for vals, weight in parts:
            win = _winners(vals)
            for p in win:
                out[p] += weight / len(win)
        return out

    def shares(self, holes: Sequence[Sequence[int]],
               boards: Sequence[Sequence[int]]) -> list[float]:
        """Fraction of the pot each player wins, splitting evenly across boards."""
        n = len(holes)
        out = [0.0] * n
        for board in boards:
            for p, s in enumerate(self.board_shares(holes, board)):
                out[p] += s / len(boards)
        return out


def split_pot(pot: int, shares: Sequence[float], odd_chip_order: Optional[Sequence[int]] = None) -> list[int]:
    """Integer chips per player for `shares` of `pot`. Odd chips go one at a time to the
    players with the largest remainders (ties: `odd_chip_order`, default big blind first)."""
    n = len(shares)
    raw = [pot * s for s in shares]
    chips = [int(x) for x in raw]
    left = pot - sum(chips)
    order = list(odd_chip_order) if odd_chip_order is not None else list(range(n - 1, -1, -1))
    ranked = sorted(range(n), key=lambda p: (-(raw[p] - chips[p]), order.index(p)))
    for p in ranked[:left]:
        chips[p] += 1
    return chips
