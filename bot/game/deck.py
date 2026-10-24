"""Deck plugin: build any deck from a DeckSpec, with lookup arrays for evaluators.

Card ids follow bot/cards.py (standard faces 0..51, jokers 52.., +64 per extra copy), so
a standard or short deck uses exactly the usual ints. Evaluators don't use raw ranks:
they use each card's *position* in the deck's rank order (0 = lowest rank present), so
straights automatically follow the deck (short deck: A-6-7-8-9 is the low straight).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Sequence

import numpy as np

from bot.cards import (COPY_STRIDE, JOKER_BASE, RANKS, SUITS, format_card, make_card,
                       parse_card)


@dataclass(frozen=True)
class Deck:
    ranks: str = RANKS          # low to high
    suits: str = SUITS
    jokers: int = 0
    copies: int = 1
    removed: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(r not in RANKS for r in self.ranks):
            raise ValueError(f"rank symbols must come from {RANKS!r}: {self.ranks!r}")
        if any(s not in SUITS for s in self.suits):
            raise ValueError(f"suit symbols must come from {SUITS!r} (more suits need a new "
                             f"card encoding): {self.suits!r}")
        if list(self.ranks) != sorted(self.ranks, key=RANKS.index):
            raise ValueError("deck ranks must be listed low to high")
        if self.jokers > COPY_STRIDE - JOKER_BASE:
            raise ValueError("too many jokers")

    @staticmethod
    def from_spec(spec) -> "Deck":
        return Deck(spec.ranks, spec.suits, spec.jokers, spec.copies, tuple(spec.removed))

    # ---- the cards
    @cached_property
    def cards(self) -> tuple[int, ...]:
        removed = {parse_card(c) for c in self.removed}
        faces = [make_card(RANKS.index(r), SUITS.index(s)) for r in self.ranks for s in self.suits]
        faces = [f for f in faces if f not in removed]
        faces += [JOKER_BASE + j for j in range(self.jokers)]
        return tuple(sorted(c * 1 + COPY_STRIDE * k for k in range(self.copies) for c in faces))

    def __len__(self) -> int:
        return len(self.cards)

    @property
    def is_standard_52(self) -> bool:
        return self.cards == tuple(range(52))

    def text(self, cards: Sequence[int]) -> str:
        return ",".join(format_card(c) for c in cards)

    # ---- lookup arrays (index = card id)
    @cached_property
    def size_ids(self) -> int:
        return max(self.cards) + 1 if self.cards else 0

    def _array(self, fn, dtype=np.int16) -> np.ndarray:
        a = np.full(max(self.size_ids, 1), -1, dtype=dtype)
        for c in self.cards:
            a[c] = fn(c % COPY_STRIDE)
        return a

    @cached_property
    def n_ranks(self) -> int:
        return len(self.ranks)

    @cached_property
    def pos_high(self) -> np.ndarray:
        """Rank position, low to high (ace highest). Jokers: -1."""
        order = {RANKS.index(r): i for i, r in enumerate(self.ranks)}
        return self._array(lambda f: order[f // 4] if f < JOKER_BASE else -1)

    @cached_property
    def pos_ace_low(self) -> np.ndarray:
        """Rank position with the ace (if present) moved to the bottom (for A-5 lowball)."""
        seq = list(self.ranks)
        if "A" in seq:
            seq = ["A"] + [r for r in seq if r != "A"]
        order = {RANKS.index(r): i for i, r in enumerate(seq)}
        return self._array(lambda f: order[f // 4] if f < JOKER_BASE else -1)

    @cached_property
    def suit(self) -> np.ndarray:
        return self._array(lambda f: f % 4 if f < JOKER_BASE else -1)

    @cached_property
    def joker(self) -> np.ndarray:
        return self._array(lambda f: f >= JOKER_BASE, dtype=np.bool_)


STANDARD_DECK = Deck()
