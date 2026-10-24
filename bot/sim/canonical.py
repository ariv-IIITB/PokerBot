"""Suit isomorphism: two hole hands are equivalent if relabelling suits maps one onto the
other (A♥K♥ ~ A♠K♠). Works for any deck (subset of ranks/suits, jokers kept as-is).

`canonical(cards)` -> a hashable canonical form; `HandClasses` enumerates every starting
hand of a given size, numbers the classes, and gives a fast lookup from cards to class id
(dict for scalars, a combinatorial-index table for NumPy batches).
Known counts: 169 classes for 2-card Hold'em hands, 1,755 for 3-card hands.
"""
from __future__ import annotations

import itertools
from functools import lru_cache
from math import comb
from typing import Sequence

import numpy as np

_PERMS = list(itertools.permutations(range(4)))


def canonical(cards: Sequence[int]) -> tuple:
    """Smallest sorted (rank, relabelled suit) tuple over all suit relabellings."""
    best = None
    for perm in _PERMS:
        form = tuple(sorted(((c % 64) // 4, perm[(c % 64) % 4]) if c % 64 < 52 else (99, c % 64)
                            for c in cards))
        if best is None or form < best:
            best = form
    return best


class HandClasses:
    """Starting-hand classes for `size` hole cards from `deck` (card ids)."""

    def __init__(self, deck: Sequence[int], size: int) -> None:
        self.deck = tuple(sorted(deck))
        self.size = size
        self.pos = {c: i for i, c in enumerate(self.deck)}
        forms: dict = {}
        combo_class = []
        self.counts: list[int] = []
        self.representative: list[tuple] = []
        for combo in itertools.combinations(self.deck, size):
            f = canonical(combo)
            cid = forms.get(f)
            if cid is None:
                cid = forms[f] = len(forms)
                self.counts.append(0)
                self.representative.append(combo)
            self.counts[cid] += 1
            combo_class.append(cid)
        self.forms = forms
        self.n_classes = len(forms)
        # combo_class is in combinations() order == combinatorial-index order of positions.
        self.table = np.array(combo_class, dtype=np.int32)
        n = len(self.deck)
        self.comb_np = np.array([[comb(i, j) for j in range(size + 1)] for i in range(n + 1)],
                                dtype=np.int64)

    def class_of(self, cards: Sequence[int]) -> int:
        return self.forms[canonical(cards)]

    def index(self) -> "ClassIndex":
        return ClassIndex(self.deck, self.size, self.table)


class ClassIndex:
    """Runtime lookup cards -> class id from a precomputed table (no enumeration needed).

    The table is in itertools.combinations order over the sorted deck; a sorted combination
    of deck positions p_0 < ... < p_{k-1} has index C(n,k) - 1 - sum_i C(n-1-p_i, k-i)."""

    def __init__(self, deck: Sequence[int], size: int, table: np.ndarray) -> None:
        self.deck = tuple(sorted(deck))
        self.size = size
        self.table = np.asarray(table)
        n = len(self.deck)
        if len(self.table) != comb(n, size):
            raise ValueError("class table does not match this deck")
        self.lut = np.full(max(self.deck) + 1, -1, dtype=np.int64)
        self.lut[list(self.deck)] = np.arange(n)
        self.comb_np = np.array([[comb(i, j) for j in range(size + 1)] for i in range(n + 1)],
                                dtype=np.int64)
        self.total = comb(n, size)

    def class_batch(self, holes: np.ndarray) -> np.ndarray:
        """Class ids for an (B, size) array of card ids."""
        p = np.sort(self.lut[np.asarray(holes)], axis=1)
        n, k = len(self.deck), self.size
        rest = np.zeros(len(p), dtype=np.int64)
        for i in range(k):
            rest += self.comb_np[n - 1 - p[:, i], k - i]
        return self.table[self.total - 1 - rest]

    def class_of(self, cards: Sequence[int]) -> int:
        return int(self.class_batch(np.array([list(cards)]))[0])


@lru_cache(maxsize=8)
def hand_classes(deck: tuple, size: int) -> HandClasses:
    return HandClasses(deck, size)
