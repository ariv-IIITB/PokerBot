"""Card encoding: a standard card is an int 0..51 = rank * 4 + suit.

rank 0..12 = 2,3,...,9,T,J,Q,K,A    suit 0..3 = c,d,h,s
Text form is two characters, e.g. "Ah", "Td". A list is comma-separated; "-" means none.

Extensions for non-standard decks (see bot/game/deck.py):
  jokers        ids 52..63          text "X0", "X1", ...
  extra copies  id + 64 * copy      text "Ah~1", "X0~2"   (copy 0 has no suffix)
So `id % 64` is the card's face, and every physical card still has a unique id.
"""
from __future__ import annotations

from typing import Iterable, Sequence

RANKS = "23456789TJQKA"
SUITS = "cdhs"
NUM_RANKS = len(RANKS)
NUM_SUITS = len(SUITS)
DECK_SIZE = NUM_RANKS * NUM_SUITS
FULL_DECK: tuple[int, ...] = tuple(range(DECK_SIZE))

JOKER_BASE = 52          # first joker face id
COPY_STRIDE = 64         # id offset between deck copies

_RANK_INDEX = {r: i for i, r in enumerate(RANKS)}
_SUIT_INDEX = {s: i for i, s in enumerate(SUITS)}


def make_card(rank: int, suit: int) -> int:
    """Card int from rank index (0=deuce .. 12=ace) and suit index (0..3)."""
    return rank * NUM_SUITS + suit


def rank_of(card: int) -> int:
    return card // NUM_SUITS


def suit_of(card: int) -> int:
    return card % NUM_SUITS


def is_joker(card: int) -> bool:
    return card % COPY_STRIDE >= JOKER_BASE


def face_of(card: int) -> int:
    """The card's face (copy suffix removed): 0..51 standard, 52..63 jokers."""
    return card % COPY_STRIDE


def parse_card(text: str) -> int:
    """Parse "Ah" -> int (also "X0" jokers and "Ah~1" copies). Case-insensitive rank and
    suit. Raises ValueError."""
    t = text.strip()
    copy = 0
    if "~" in t:
        t, _, c = t.partition("~")
        if not c.isdigit() or int(c) < 1:
            raise ValueError(f"bad card {text!r}")
        copy = int(c)
    if len(t) == 2 and t[0] in "Xx" and t[1].isdigit():
        return COPY_STRIDE * copy + JOKER_BASE + int(t[1])
    if len(t) != 2:
        raise ValueError(f"bad card {text!r}")
    rank = _RANK_INDEX.get(t[0].upper())
    suit = _SUIT_INDEX.get(t[1].lower())
    if rank is None or suit is None:
        raise ValueError(f"bad card {text!r}")
    return COPY_STRIDE * copy + make_card(rank, suit)


def format_card(card: int) -> str:
    if card < 0:
        raise ValueError(f"card out of range: {card}")
    copy, face = divmod(card, COPY_STRIDE)
    if face >= JOKER_BASE:
        text = f"X{face - JOKER_BASE}"
    elif face < DECK_SIZE:
        text = RANKS[rank_of(face)] + SUITS[suit_of(face)]
    else:
        raise ValueError(f"card out of range: {card}")
    return text + (f"~{copy}" if copy else "")


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
