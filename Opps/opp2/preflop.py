"""
preflop.py - 169-hand canonical mapping and precomputed Nash push/fold thresholds.
"""

from typing import Dict, List, Tuple
import numpy as np
from evaluator import RANK_CHARS

CANONICAL_NAMES: List[str] = []
NAME_TO_INDEX: Dict[str, int] = {}


def _init_canonical_hands() -> None:
    for r in range(12, -1, -1):
        name = f"{RANK_CHARS[r]}{RANK_CHARS[r]}"
        NAME_TO_INDEX[name] = len(CANONICAL_NAMES)
        CANONICAL_NAMES.append(name)

    for r1 in range(12, -1, -1):
        for r2 in range(r1 - 1, -1, -1):
            name = f"{RANK_CHARS[r1]}{RANK_CHARS[r2]}s"
            NAME_TO_INDEX[name] = len(CANONICAL_NAMES)
            CANONICAL_NAMES.append(name)

    for r1 in range(12, -1, -1):
        for r2 in range(r1 - 1, -1, -1):
            name = f"{RANK_CHARS[r1]}{RANK_CHARS[r2]}o"
            NAME_TO_INDEX[name] = len(CANONICAL_NAMES)
            CANONICAL_NAMES.append(name)


_init_canonical_hands()


def cards_to_canonical(c1: int, c2: int) -> Tuple[int, str]:
    r1, s1 = c1 >> 2, c1 & 3
    r2, s2 = c2 >> 2, c2 & 3

    if r1 < r2:
        r1, r2, s1, s2 = r2, r1, s2, s1

    if r1 == r2:
        name = f"{RANK_CHARS[r1]}{RANK_CHARS[r2]}"
    elif s1 == s2:
        name = f"{RANK_CHARS[r1]}{RANK_CHARS[r2]}s"
    else:
        name = f"{RANK_CHARS[r1]}{RANK_CHARS[r2]}o"

    return NAME_TO_INDEX[name], name


NASH_SB_PUSH_THRESHOLDS: Dict[str, float] = {
    "AA": 100.0, "KK": 100.0, "QQ": 100.0, "JJ": 100.0, "TT": 100.0,
    "99": 25.0,  "88": 20.0,  "77": 16.0,  "66": 14.0,  "55": 12.0,
    "44": 10.0,  "33": 8.5,   "22": 7.5,
    "AKs": 100.0, "AQs": 100.0, "AJs": 35.0, "ATs": 25.0, "A9s": 18.0,
    "A8s": 15.0,  "A7s": 14.0,  "A6s": 12.5, "A5s": 14.0, "A4s": 13.0,
    "A3s": 11.5,  "A2s": 10.5,
    "KQs": 25.0,  "KJs": 20.0,  "KTs": 16.0, "K9s": 12.5, "K8s": 9.5,
    "K7s": 8.0,   "K6s": 7.5,   "K5s": 7.0,  "K4s": 6.5,  "K3s": 6.0,
    "QJs": 16.0,  "QTs": 13.0,  "Q9s": 10.0, "Q8s": 7.5,  "JTs": 13.0,
    "J9s": 9.5,   "T9s": 9.0,   "98s": 8.0,  "87s": 7.5,  "76s": 6.5,
    "AKo": 100.0, "AQo": 35.0,  "AJo": 20.0, "ATo": 16.0, "A9o": 12.0,
    "A8o": 10.0,  "A7o": 8.5,   "A6o": 7.5,  "A5o": 8.0,  "A4o": 7.0,
    "KQo": 16.0,  "KJo": 12.5,  "KTo": 9.5,  "QJo": 9.5,
}

NASH_BB_CALL_THRESHOLDS: Dict[str, float] = {
    "AA": 100.0, "KK": 100.0, "QQ": 100.0, "JJ": 100.0, "TT": 25.0,
    "99": 18.0,  "88": 14.0,  "77": 11.0,  "66": 8.5,   "55": 7.0,
    "44": 5.5,   "33": 4.5,   "22": 4.0,
    "AKs": 100.0, "AQs": 35.0, "AJs": 20.0, "ATs": 15.0, "A9s": 11.0,
    "A8s": 9.0,   "A7s": 8.0,  "A6s": 7.0,  "A5s": 7.5,  "A4s": 6.5,
    "KQs": 15.0,  "KJs": 11.0, "KTs": 8.5,  "QJs": 8.5,
    "AKo": 35.0,  "AQo": 18.0, "AJo": 12.5, "ATo": 9.5,  "A9o": 7.0,
    "KQo": 9.0,
}


def should_sb_jam(canonical_name: str, eff_stack_bb: float) -> bool:
    threshold = NASH_SB_PUSH_THRESHOLDS.get(canonical_name, 0.0)
    return eff_stack_bb <= threshold


def should_bb_call_jam(canonical_name: str, eff_stack_bb: float) -> bool:
    threshold = NASH_BB_CALL_THRESHOLDS.get(canonical_name, 0.0)
    return eff_stack_bb <= threshold


SB_OPEN_NAMES = set(
    [name for name in CANONICAL_NAMES if not (
        name.endswith("o") and int(RANK_CHARS.index(name[0])) <= 4 and int(RANK_CHARS.index(name[1])) <= 3
    )]
)
