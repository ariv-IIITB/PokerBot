"""Generic poker hand evaluator: best `hand_size`-card hand from hole + board cards.

How it works
------------
A k-card hand (k <= 5) is scored from two small lookup tables, built once in memory:
  * FLUSH table, indexed by the 13-bit mask of ranks (used when all k suits match)
  * MULTI table, indexed by the rank multiset (sorted ranks -> combinatorial index;
    13 ranks, 5 cards -> only 6188 entries)
The best hand from N cards is the max over all k-card combinations (respecting the
optional "exactly u hole cards" rule). `evaluate_batch` does the same with NumPy for many
hands at once.

Hand values are ints; higher wins, equal = split. Layout:
    category << 20 | ranks packed 4 bits each (most important first)
Categories follow standard poker order. Straights/flushes need all k cards and only exist
for k >= 3; the wheel (A-2-3-4-5, or A-2-..-(k) for smaller k) counts as a straight.
Inputs are not checked for duplicate cards (that's the caller's job, for speed).
"""
from __future__ import annotations

import itertools
from collections import Counter
from functools import lru_cache
from math import comb
from typing import Optional, Sequence

import numpy as np

from bot.cards import NUM_RANKS

HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)
CATEGORY_NAMES = ("high card", "pair", "two pair", "trips", "straight", "flush",
                  "full house", "quads", "straight flush")
CATEGORY_SHIFT = 20
MAX_HAND_SIZE = 5


def category(value: int) -> int:
    """Hand category (HIGH_CARD..STRAIGHT_FLUSH) of an evaluator value."""
    return int(value) >> CATEGORY_SHIFT


# --------------------------------------------------------------------------- scoring

def _straight_top(distinct_desc: list[int], k: int) -> Optional[int]:
    """Top rank if the k distinct ranks form a straight (ace may play low), else None."""
    if k < 3 or len(distinct_desc) != k:
        return None
    if distinct_desc[0] - distinct_desc[-1] == k - 1:
        return distinct_desc[0]
    wheel = [NUM_RANKS - 1] + list(range(k - 2, -1, -1))  # A, then k-1 lowest ranks
    if distinct_desc == wheel:
        return k - 2
    return None


def score_ranks(ranks: Sequence[int], flush: bool) -> int:
    """Value of a k-card hand given its ranks and whether all suits match."""
    k = len(ranks)
    counts = Counter(ranks)
    # Order ranks by (count, rank) descending: e.g. full house -> trips rank first.
    groups = sorted(counts.items(), key=lambda rc: (rc[1], rc[0]), reverse=True)
    ordered = [r for r, c in groups for _ in range(c)]
    shape = [c for _, c in groups]
    flush = flush and k >= 3
    top = _straight_top(sorted(counts, reverse=True), k)

    if top is not None and flush:
        cat, ordered = STRAIGHT_FLUSH, [top]
    elif shape[0] == 4:
        cat = QUADS
    elif shape[:2] == [3, 2]:
        cat = FULL_HOUSE
    elif flush:
        cat = FLUSH
    elif top is not None:
        cat, ordered = STRAIGHT, [top]
    elif shape[0] == 3:
        cat = TRIPS
    elif shape[:2] == [2, 2]:
        cat = TWO_PAIR
    elif shape[0] == 2:
        cat = PAIR
    else:
        cat = HIGH_CARD
    packed = 0
    for i, r in enumerate(ordered):
        packed |= r << (4 * (MAX_HAND_SIZE - 1 - i))
    return (cat << CATEGORY_SHIFT) | packed


# --------------------------------------------------------------------------- tables

def _multiset_index(sorted_ranks: Sequence[int]) -> int:
    """Combinatorial index of a sorted rank multiset (r0 <= r1 <= ...)."""
    return sum(comb(r + i, i + 1) for i, r in enumerate(sorted_ranks))


class _Tables:
    """Lookup tables for one hand size k. Built lazily; tiny (a few thousand entries)."""

    def __init__(self, k: int) -> None:
        if not 1 <= k <= MAX_HAND_SIZE:
            raise ValueError(f"hand_size must be 1..{MAX_HAND_SIZE}, got {k}")
        self.k = k
        multi = np.full(comb(NUM_RANKS + k - 1, k), -1, dtype=np.int64)
        for ms in itertools.combinations_with_replacement(range(NUM_RANKS), k):
            if max(Counter(ms).values()) <= 4:          # at most 4 cards per rank
                multi[_multiset_index(ms)] = score_ranks(ms, flush=False)
        flush = np.full(1 << NUM_RANKS, -1, dtype=np.int64)
        for rs in itertools.combinations(range(NUM_RANKS), k):
            flush[sum(1 << r for r in rs)] = score_ranks(rs, flush=True)
        # Binomial table for vectorized multiset indexing: COMB[n, j] = C(n, j).
        n_max = NUM_RANKS + k
        self.comb_np = np.array([[comb(n, j) for j in range(k + 1)] for n in range(n_max)],
                                dtype=np.int64)
        self.multi_np, self.flush_np = multi, flush
        # Plain lists are much faster than NumPy for scalar indexing.
        self.multi_py = multi.tolist()
        self.flush_py = flush.tolist()
        self.comb_py = self.comb_np.tolist()

    def eval_py(self, cards: Sequence[int]) -> int:
        """Score one k-card hand (pure Python)."""
        ranks = sorted(c >> 2 for c in cards)
        s0 = cards[0] & 3
        if all((c & 3) == s0 for c in cards):
            m = 0
            for r in ranks:
                m |= 1 << r
            return self.flush_py[m]
        cp = self.comb_py
        return self.multi_py[sum(cp[r + i][i + 1] for i, r in enumerate(ranks))]

    def eval_np(self, cards: np.ndarray, presorted: bool = False) -> np.ndarray:
        """Score k-card hands; `cards` has shape (..., k). Returns int64 of shape (...).
        presorted=True skips the sort when each hand's cards are already ascending."""
        ranks = cards >> 2
        suits = cards & 3
        is_flush = (suits == suits[..., :1]).all(axis=-1)
        mask = np.bitwise_or.reduce(np.left_shift(1, ranks), axis=-1)
        sr = ranks if presorted else np.sort(ranks, axis=-1)
        idx = self.comb_np[sr[..., 0], 1]
        for i in range(1, self.k):
            idx = idx + self.comb_np[sr[..., i] + i, i + 1]
        return np.where(is_flush, self.flush_np[mask], self.multi_np[idx])


@lru_cache(maxsize=None)
def tables(k: int) -> _Tables:
    return _Tables(k)


# --------------------------------------------------------------------------- evaluator

class GenericEvaluator:
    """Best `hand_size`-card hand from hole + board.

    hole_cards_used=None: any mix of hole and board cards.
    hole_cards_used=u:    exactly u hole cards and hand_size - u board cards (Omaha: u=2).
    """

    def __init__(self, hand_size: int = 5, hole_cards_used: Optional[int] = None) -> None:
        self.hand_size = hand_size
        self.hole_cards_used = hole_cards_used
        self._t = tables(hand_size)

    @lru_cache(maxsize=64)
    def combos(self, n_hole: int, n_board: int) -> tuple[tuple[int, ...], ...]:
        """Index tuples into (hole + board) for every allowed k-card combination."""
        k, u = self.hand_size, self.hole_cards_used
        if u is None:
            if n_hole + n_board < k:
                raise ValueError(f"need {k} cards, got {n_hole + n_board}")
            return tuple(itertools.combinations(range(n_hole + n_board), k))
        if n_hole < u or n_board < k - u:
            raise ValueError(f"need {u} hole + {k - u} board cards, got {n_hole} + {n_board}")
        board_idx = range(n_hole, n_hole + n_board)
        return tuple(h + b for h in itertools.combinations(range(n_hole), u)
                     for b in itertools.combinations(board_idx, k - u))

    @lru_cache(maxsize=64)
    def _combos_np(self, n_hole: int, n_board: int) -> np.ndarray:
        return np.array(self.combos(n_hole, n_board), dtype=np.intp)

    def evaluate(self, hole: Sequence[int], board: Sequence[int]) -> int:
        """Value of the best hand for one player (pure Python, no NumPy overhead)."""
        cards = list(hole) + list(board)
        ev = self._t.eval_py
        return max(ev([cards[i] for i in combo]) for combo in self.combos(len(hole), len(board)))

    def evaluate_batch(self, hole: np.ndarray, board: np.ndarray) -> np.ndarray:
        """Best-hand values for many players at once.

        hole: (B, h) or (h,);  board: (B, b) or (b,). 1-D inputs are broadcast over the
        batch. Returns an int64 array of shape (B,).
        """
        hole = np.atleast_2d(np.asarray(hole, dtype=np.intp))
        board = np.asarray(board, dtype=np.intp)
        board = board.reshape(1, -1) if board.ndim == 1 else board
        n = max(hole.shape[0], board.shape[0])
        hole = np.broadcast_to(hole, (n, hole.shape[1]))
        board = np.broadcast_to(board, (n, board.shape[1]))
        cards = np.concatenate([hole, board], axis=1)
        # With no hole/board restriction, sort each hand once: combos pick ascending
        # positions, so every k-card subset is then already sorted by rank.
        presorted = self.hole_cards_used is None
        if presorted:
            cards = np.sort(cards, axis=1)
        sub = cards[:, self._combos_np(hole.shape[1], board.shape[1])]   # (B, M, k)
        return self._t.eval_np(sub, presorted).max(axis=1)

    def evaluate_5(self, cards: Sequence[int]) -> int:
        """Score exactly `hand_size` cards (no combination search)."""
        return self._t.eval_py(list(cards))
