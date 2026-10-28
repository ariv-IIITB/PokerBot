"""
evaluator.py - Ultra-fast 7-card poker hand evaluator in Python 3.11 + NumPy.
Uses 13-bit rank bitmasks and precomputed lookup tables for O(1) flush/straight checks.
"""

from typing import Iterable, List, Sequence, Tuple
import numpy as np

RANK_CHARS = "23456789TJQKA"
SUIT_CHARS = "shdc"

CAT_HIGH_CARD = 0
CAT_ONE_PAIR = 1
CAT_TWO_PAIR = 2
CAT_THREE_OF_A_KIND = 3
CAT_STRAIGHT = 4
CAT_FLUSH = 5
CAT_FULL_HOUSE = 6
CAT_FOUR_OF_A_KIND = 7
CAT_STRAIGHT_FLUSH = 8

STRAIGHT_LOOKUP = np.full(8192, -1, dtype=np.int32)
FLUSH_LOOKUP = np.zeros(8192, dtype=np.uint32)
UNIQUE5_LOOKUP = np.zeros(8192, dtype=np.uint32)
POW13 = np.array([13**4, 13**3, 13**2, 13**1, 1], dtype=np.uint32)


def _init_lookup_tables() -> None:
    for mask in range(8192):
        s = (
            mask
            & (mask >> 1)
            & (mask >> 2)
            & (mask >> 3)
            & (mask >> 4)
        )
        if s > 0:
            highest_bit = s.bit_length() - 1
            STRAIGHT_LOOKUP[mask] = highest_bit + 4
        elif (mask & 0x100F) == 0x100F:
            STRAIGHT_LOOKUP[mask] = 3

        bits = []
        for r in range(12, -1, -1):
            if (mask >> r) & 1:
                bits.append(r)

        if len(bits) >= 5:
            top5 = np.array(bits[:5], dtype=np.uint32)
            tie5 = int(np.dot(top5, POW13))

            str_high = STRAIGHT_LOOKUP[mask]
            if str_high >= 0:
                FLUSH_LOOKUP[mask] = (CAT_STRAIGHT_FLUSH << 20) | str_high
            else:
                FLUSH_LOOKUP[mask] = (CAT_FLUSH << 20) | tie5

            if str_high >= 0:
                UNIQUE5_LOOKUP[mask] = (CAT_STRAIGHT << 20) | str_high
            else:
                UNIQUE5_LOOKUP[mask] = (CAT_HIGH_CARD << 20) | tie5


_init_lookup_tables()


def card_from_str(s: str) -> int:
    r = RANK_CHARS.index(s[0].upper())
    suit = SUIT_CHARS.index(s[1].lower())
    return (r << 2) | suit


def card_to_str(card: int) -> str:
    return f"{RANK_CHARS[card >> 2]}{SUIT_CHARS[card & 3]}"


def evaluate_7cards(cards: Sequence[int]) -> int:
    suit_counts = [0, 0, 0, 0]
    suit_masks = [0, 0, 0, 0]
    rank_counts = [0] * 13
    rank_mask = 0

    for c in cards:
        r = c >> 2
        s = c & 3
        suit_counts[s] += 1
        suit_masks[s] |= 1 << r
        rank_counts[r] += 1
        rank_mask |= 1 << r

    for s in range(4):
        if suit_counts[s] >= 5:
            return int(FLUSH_LOOKUP[suit_masks[s]])

    quad = -1
    trip1 = -1
    trip2 = -1
    pair1 = -1
    pair2 = -1
    kickers: List[int] = []

    for r in range(12, -1, -1):
        cnt = rank_counts[r]
        if cnt == 4:
            quad = r
        elif cnt == 3:
            if trip1 == -1:
                trip1 = r
            elif trip2 == -1:
                trip2 = r
        elif cnt == 2:
            if pair1 == -1:
                pair1 = r
            elif pair2 == -1:
                pair2 = r
            else:
                kickers.append(r)
        elif cnt == 1:
            kickers.append(r)

    if quad >= 0:
        kicker = kickers[0] if kickers else (trip1 if trip1 >= 0 else pair1)
        return (CAT_FOUR_OF_A_KIND << 20) | (quad * 13 + kicker)

    if trip1 >= 0 and (trip2 >= 0 or pair1 >= 0):
        second = trip2 if trip2 >= 0 else pair1
        return (CAT_FULL_HOUSE << 20) | (trip1 * 13 + second)

    str_high = int(STRAIGHT_LOOKUP[rank_mask])
    if str_high >= 0:
        return (CAT_STRAIGHT << 20) | str_high

    if trip1 >= 0:
        return (CAT_THREE_OF_A_KIND << 20) | (trip1 * 169 + kickers[0] * 13 + kickers[1])

    if pair1 >= 0 and pair2 >= 0:
        return (CAT_TWO_PAIR << 20) | (pair1 * 169 + pair2 * 13 + kickers[0])

    if pair1 >= 0:
        return (CAT_ONE_PAIR << 20) | (
            pair1 * 2197 + kickers[0] * 169 + kickers[1] * 13 + kickers[2]
        )

    return int(UNIQUE5_LOOKUP[rank_mask])


def evaluate_7cards_batch(hands_arr: np.ndarray) -> np.ndarray:
    n = hands_arr.shape[0]
    scores = np.empty(n, dtype=np.uint32)
    for i in range(n):
        scores[i] = evaluate_7cards(hands_arr[i])
    return scores
