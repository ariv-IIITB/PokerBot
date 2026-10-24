"""Card encoding: a card is an int 0..51 = rank * 4 + suit.

rank 0..12 = 2,3,...,9,T,J,Q,K,A    suit 0..3 = c,d,h,s
Text form is two characters, e.g. "Ah", "Td". A list is comma-separated; "-" means none.
"""
from __future__ import annotations

from typing import Iterable, Sequence

RANKS = "23456789TJQKA"
SUITS = "cdhs"
NUM_RANKS = len(RANKS)
NUM_SUITS = len(SUITS)
DECK_SIZE = NUM_RANKS * NUM_SUITS
FULL_DECK: tuple[int, ...] = tuple(range(DECK_SIZE))

_RANK_INDEX = {r: i for i, r in enumerate(RANKS)}
_SUIT_INDEX = {s: i for i, s in enumerate(SUITS)}


def make_card(rank: int, suit: int) -> int:
    """Card int from rank index (0=deuce .. 12=ace) and suit index (0..3)."""
    return rank * NUM_SUITS + suit


def rank_of(card: int) -> int:
    return card // NUM_SUITS


def suit_of(card: int) -> int:
    return card % NUM_SUITS


def parse_card(text: str) -> int:
    """Parse "Ah" -> int. Rank is case-insensitive, suit too. Raises ValueError."""
    t = text.strip()
    if len(t) != 2:
        raise ValueError(f"bad card {text!r}")
    rank = _RANK_INDEX.get(t[0].upper())
    suit = _SUIT_INDEX.get(t[1].lower())
    if rank is None or suit is None:
        raise ValueError(f"bad card {text!r}")
    return make_card(rank, suit)


def format_card(card: int) -> str:
    if not 0 <= card < DECK_SIZE:
        raise ValueError(f"card out of range: {card}")
    return RANKS[rank_of(card)] + SUITS[suit_of(card)]


def parse_cards(text: str) -> tuple[int, ...]:
    """Parse "Ah,Kd" -> (int, int). "-" or "" -> (). Raises ValueError on duplicates."""
    t = text.strip()
    if t in ("", "-"):
        return ()
    cards = tuple(parse_card(part) for part in t.split(","))
    if len(set(cards)) != len(cards):
        raise ValueError(f"duplicate cards in {text!r}")
    return cards


def format_cards(cards: Iterable[int]) -> str:
    parts = [format_card(c) for c in cards]
    return ",".join(parts) if parts else "-"


def remaining_deck(exclude: Sequence[int] = ()) -> list[int]:
    """All cards not in `exclude`, in ascending order."""
    dead = set(exclude)
    return [c for c in FULL_DECK if c not in dead]
