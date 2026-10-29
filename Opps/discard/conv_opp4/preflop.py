"""
preflop.py - 169-hand canonical mapping and preflop ranges stratified by:
- Effective stacks: <=8 BB, 8-15 BB, 15-30 BB, 30-60 BB, >60 BB
- Position: Button/SB vs Big Blind
- Previous action: unopened, facing limp, facing open raise, facing 3-bet
Includes dedicated push/fold charts at <=8 BB.
"""

from typing import Dict, List, Set, Tuple
import numpy as np

RANK_CHARS = "23456789TJQKA"
SUIT_CHARS = "shdc"

# Generate all 1,326 two-card combinations
COMBO_LIST: List[Tuple[int, int]] = []
COMBO_INDEX = np.full((52, 52), -1, dtype=np.int32)
for _c1 in range(52):
    for _c2 in range(_c1 + 1, 52):
        idx = len(COMBO_LIST)
        COMBO_LIST.append((_c1, _c2))
        COMBO_INDEX[_c1, _c2] = idx
        COMBO_INDEX[_c2, _c1] = idx

TOTAL_COMBOS = len(COMBO_LIST)  # Exactly 1326


def cards_to_canonical(c1: int, c2: int) -> Tuple[str, bool, bool]:
    """
    Converts two cards into canonical 169-hand representation.
    Returns: (canonical_name, is_pair, is_suited)
    """
    r1 = c1 >> 2
    s1 = c1 & 3
    r2 = c2 >> 2
    s2 = c2 & 3

    if r1 == r2:
        return f"{RANK_CHARS[r1]}{RANK_CHARS[r2]}", True, False
    elif r1 > r2:
        suffix = "s" if s1 == s2 else "o"
        return f"{RANK_CHARS[r1]}{RANK_CHARS[r2]}{suffix}", False, (s1 == s2)
    else:
        suffix = "s" if s1 == s2 else "o"
        return f"{RANK_CHARS[r2]}{RANK_CHARS[r1]}{suffix}", False, (s1 == s2)


# Precompute canonical name for all 1,326 combos
COMBO_CANONICAL: List[str] = [
    cards_to_canonical(c1, c2)[0] for (c1, c2) in COMBO_LIST
]

# 169 Canonical Hand Strength Order (Rough HUNL starting hand percentile)
ALL_PAIRS = [f"{r}{r}" for r in reversed(RANK_CHARS)]

# Tier 0: <= 8 BB (Dedicated Sklansky-Chubukov / Nash Push-Fold Charts)
PUSH_FOLD_SB_JAM_8BB: Set[str] = set(
    ALL_PAIRS
    + [f"A{r}s" for r in RANK_CHARS[:-1]]
    + [f"A{r}o" for r in RANK_CHARS[:-1]]
    + [f"K{r}s" for r in RANK_CHARS[:-2]]
    + [f"K{r}o" for r in "6789TJQ"]
    + [f"Q{r}s" for r in "456789TJ"]
    + [f"Q{r}o" for r in "789TJ"]
    + [f"J{r}s" for r in "6789T"]
    + [f"J{r}o" for r in "89T"]
    + ["T9s", "T8s", "T7s", "T9o", "T8o", "98s", "97s", "87s", "76s", "65s", "54s"]
)

PUSH_FOLD_BB_CALL_8BB: Set[str] = set(
    ALL_PAIRS
    + [f"A{r}s" for r in RANK_CHARS[:-1]]
    + [f"A{r}o" for r in "56789TJQ"]
    + [f"K{r}s" for r in "89TJQ"]
    + [f"K{r}o" for r in "9TJQ"]
    + [f"Q{r}s" for r in "9TJ"]
    + ["QTo", "QJo", "JTs", "JTo", "T9s"]
)

# Stack stratified preflop opening and defense ranges
PREFLOP_CHARTS: Dict[str, Dict[str, Set[str]]] = {
    # 1. <= 8 BB
    "tier_8bb": {
        "sb_open": PUSH_FOLD_SB_JAM_8BB,
        "sb_vs_3bet": {"AA", "KK", "QQ", "JJ", "TT", "99", "88", "AKs", "AKo", "AQs", "AQo"},
        "bb_defend_call": PUSH_FOLD_BB_CALL_8BB,
        "bb_3bet": {"AA", "KK", "QQ", "JJ", "TT", "AKs", "AKo"},
        "bb_vs_limp": PUSH_FOLD_SB_JAM_8BB,
    },
    # 2. 8-15 BB
    "tier_15bb": {
        "sb_open": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in "23456789TJQ"]
            + [f"K{r}s" for r in "23456789TJQ"]
            + [f"K{r}o" for r in "6789TJQ"]
            + [f"Q{r}s" for r in "6789TJ"]
            + [f"Q{r}o" for r in "89TJ"]
            + [f"J{r}s" for r in "789T"]
            + [f"J{r}o" for r in "89T"]
            + ["T9s", "T8s", "98s", "87s", "76s", "65s"]
        ),
        "sb_vs_3bet": {"AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "AKs", "AKo", "AQs", "AQo", "AJs"},
        "bb_defend_call": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in "6789TJQ"]
            + [f"K{r}s" for r in "789TJQ"]
            + [f"K{r}o" for r in "89TJQ"]
            + [f"Q{r}s" for r in "89TJ"]
            + [f"Q{r}o" for r in "9TJ"]
            + ["JTs", "J9s", "T9s", "98s", "87s"]
        ),
        "bb_3bet": {"AA", "KK", "QQ", "JJ", "TT", "99", "AKs", "AKo", "AQs", "A5s", "A4s"},
        "bb_vs_limp": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in "789TJQ"]
            + [f"K{r}s" for r in "789TJQ"]
            + [f"K{r}o" for r in "89TJQ"]
            + ["QJs", "QJo", "QTs", "JTs"]
        ),
    },
    # 3. 15-30 BB
    "tier_30bb": {
        "sb_open": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in RANK_CHARS[:-1]]
            + [f"K{r}s" for r in RANK_CHARS[:-2]]
            + [f"K{r}o" for r in "56789TJQ"]
            + [f"Q{r}s" for r in "456789TJ"]
            + [f"Q{r}o" for r in "789TJ"]
            + [f"J{r}s" for r in "6789T"]
            + [f"J{r}o" for r in "789T"]
            + ["T9s", "T8s", "T7s", "T9o", "98s", "97s", "87s", "76s", "65s", "54s"]
        ),
        "sb_vs_3bet": {"AA", "KK", "QQ", "JJ", "TT", "99", "88", "AKs", "AKo", "AQs", "AQo", "AJs", "KQs"},
        "bb_defend_call": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in "23456789TJQ"]
            + [f"K{r}s" for r in RANK_CHARS[:-2]]
            + [f"K{r}o" for r in "6789TJQ"]
            + [f"Q{r}s" for r in "6789TJ"]
            + [f"Q{r}o" for r in "89TJ"]
            + [f"J{r}s" for r in "789T"]
            + ["JTo", "T9s", "T8s", "98s", "87s", "76s", "65s", "54s"]
        ),
        "bb_3bet": {"AA", "KK", "QQ", "JJ", "TT", "99", "AKs", "AKo", "AQs", "AQo", "A5s", "A4s", "KQs"},
        "bb_vs_limp": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in "89TJQ"]
            + [f"K{r}s" for r in "89TJQ"]
            + ["QJs", "QJo", "QTs", "JTs"]
        ),
    },
    # 4. 30-60 BB
    "tier_60bb": {
        "sb_open": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in RANK_CHARS[:-1]]
            + [f"K{r}s" for r in RANK_CHARS[:-2]]
            + [f"K{r}o" for r in "456789TJQ"]
            + [f"Q{r}s" for r in "3456789TJ"]
            + [f"Q{r}o" for r in "6789TJ"]
            + [f"J{r}s" for r in "56789T"]
            + [f"J{r}o" for r in "789T"]
            + ["T9s", "T8s", "T7s", "T9o", "98s", "97s", "96s", "87s", "86s", "76s", "65s", "54s"]
        ),
        "sb_vs_3bet": {"AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "AKs", "AKo", "AQs", "AQo", "AJs", "KQs", "KJs", "QJs"},
        "bb_defend_call": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in RANK_CHARS[:-1]]
            + [f"K{r}s" for r in RANK_CHARS[:-2]]
            + [f"K{r}o" for r in "56789TJQ"]
            + [f"Q{r}s" for r in "56789TJ"]
            + [f"Q{r}o" for r in "789TJ"]
            + [f"J{r}s" for r in "6789T"]
            + [f"J{r}o" for r in "89T"]
            + ["T9s", "T8s", "98s", "87s", "76s", "65s", "54s"]
        ),
        "bb_3bet": {"AA", "KK", "QQ", "JJ", "TT", "99", "88", "AKs", "AKo", "AQs", "AQo", "A5s", "A4s", "A3s", "KQs", "KJs", "QJs"},
        "bb_vs_limp": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in "789TJQ"]
            + [f"K{r}s" for r in "789TJQ"]
            + ["QJs", "QJo", "QTs", "JTs", "T9s"]
        ),
    },
    # 5. > 60 BB (Deep stack)
    "tier_deep": {
        "sb_open": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in RANK_CHARS[:-1]]
            + [f"K{r}s" for r in RANK_CHARS[:-2]]
            + [f"K{r}o" for r in "3456789TJQ"]
            + [f"Q{r}s" for r in "23456789TJ"]
            + [f"Q{r}o" for r in "6789TJ"]
            + [f"J{r}s" for r in "456789T"]
            + [f"J{r}o" for r in "789T"]
            + ["T9s", "T8s", "T7s", "T6s", "T9o", "98s", "97s", "96s", "87s", "86s", "76s", "65s", "54s", "43s"]
        ),
        "sb_vs_3bet": {"AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "66", "AKs", "AKo", "AQs", "AQo", "AJs", "AJo", "ATs", "KQs", "KJs", "QJs", "JTs"},
        "bb_defend_call": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in RANK_CHARS[:-1]]
            + [f"K{r}s" for r in RANK_CHARS[:-2]]
            + [f"K{r}o" for r in "456789TJQ"]
            + [f"Q{r}s" for r in "456789TJ"]
            + [f"Q{r}o" for r in "6789TJ"]
            + [f"J{r}s" for r in "56789T"]
            + [f"J{r}o" for r in "789T"]
            + ["T9s", "T8s", "98s", "87s", "76s", "65s", "54s", "43s"]
        ),
        "bb_3bet": {"AA", "KK", "QQ", "JJ", "TT", "99", "88", "AKs", "AKo", "AQs", "AQo", "A5s", "A4s", "A3s", "A2s", "KQs", "KJs", "QJs", "T9s", "98s"},
        "bb_vs_limp": set(
            ALL_PAIRS
            + [f"A{r}s" for r in RANK_CHARS[:-1]]
            + [f"A{r}o" for r in "6789TJQ"]
            + [f"K{r}s" for r in "6789TJQ"]
            + [f"K{r}o" for r in "89TJQ"]
            + ["QJs", "QJo", "QTs", "JTs", "T9s", "98s"]
        ),
    },
}


def get_tier_name(eff_stack_bb: float) -> str:
    """Classifies effective stack into one of the 5 tiers."""
    if eff_stack_bb <= 8.0:
        return "tier_8bb"
    elif eff_stack_bb <= 15.0:
        return "tier_15bb"
    elif eff_stack_bb <= 30.0:
        return "tier_30bb"
    elif eff_stack_bb <= 60.0:
        return "tier_60bb"
    else:
        return "tier_deep"


def is_hand_in_chart(canonical: str, eff_stack_bb: float, chart_key: str) -> bool:
    """Checks whether a canonical hand is in the designated stack-stratified chart."""
    tier = get_tier_name(eff_stack_bb)
    chart = PREFLOP_CHARTS[tier].get(chart_key, set())
    return canonical in chart


def _combos(canonical: str) -> int:
    if len(canonical) == 2:
        return 6
    return 4 if canonical.endswith("s") else 12


# Share of all starting hands each chart contains: {(tier, chart_key): fraction}
CHART_SHARE: Dict[Tuple[str, str], float] = {
    (tier, key): sum(_combos(h) for h in hands) / float(TOTAL_COMBOS)
    for tier, charts in PREFLOP_CHARTS.items()
    for key, hands in charts.items()
}


def hand_in_chart(hero_cards, eff_stack_bb: float, chart_key: str) -> bool:
    """Chart lookup for a 2-card hand, or for a 3-card Discard Hold'em hand (by frequency:
    its best keep must be inside the top share of hands the chart contains)."""
    if len(hero_cards) == 2:
        canonical, _, _ = cards_to_canonical(hero_cards[0], hero_cards[1])
        return is_hand_in_chart(canonical, eff_stack_bb, chart_key)
    from keep3 import percentile
    share = CHART_SHARE.get((get_tier_name(eff_stack_bb), chart_key), 0.0)
    return percentile(hero_cards) >= 1.0 - share
