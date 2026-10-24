"""Slow, obviously-correct reference evaluator, written independently of bot/evaluator.py.

Returns comparable tuples (category, tiebreak ranks...) using ranks 2..14.
Straights/flushes need all k cards and k >= 3 (same documented rule as the evaluator).
"""
from __future__ import annotations

import itertools
from typing import Optional, Sequence

HC, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, SF = range(9)


def ref_score(cards: Sequence[int]) -> tuple:
    k = len(cards)
    ranks = sorted((c // 4 + 2 for c in cards), reverse=True)
    suits = {c % 4 for c in cards}
    flush = k >= 3 and len(suits) == 1

    distinct = sorted(set(ranks), reverse=True)
    straight_high = None
    if k >= 3 and len(distinct) == k:
        if distinct[0] - distinct[-1] == k - 1:
            straight_high = distinct[0]
        elif distinct == [14] + list(range(k, 1, -1)):   # ace-low, e.g. A5432
            straight_high = k

    count = {r: ranks.count(r) for r in distinct}
    quads = [r for r in distinct if count[r] == 4]
    trips = [r for r in distinct if count[r] == 3]
    pairs = [r for r in distinct if count[r] == 2]
    singles = [r for r in distinct if count[r] == 1]

    if straight_high and flush:
        return (SF, straight_high)
    if quads:
        return (QUADS, quads[0], *singles)
    if trips and pairs:
        return (FULL_HOUSE, trips[0], pairs[0])
    if flush:
        return (FLUSH, *ranks)
    if straight_high:
        return (STRAIGHT, straight_high)
    if trips:
        return (TRIPS, trips[0], *singles)
    if len(pairs) >= 2:
        return (TWO_PAIR, pairs[0], pairs[1], *singles)
    if pairs:
        return (PAIR, pairs[0], *singles)
    return (HC, *ranks)


def ref_best(hole: Sequence[int], board: Sequence[int], k: int = 5,
             used: Optional[int] = None) -> tuple:
    if used is None:
        return max(ref_score(c) for c in itertools.combinations(list(hole) + list(board), k))
    return max(ref_score(h + b) for h in itertools.combinations(hole, used)
               for b in itertools.combinations(board, k - used))


# =========================================================================== phase 12
# General references: rank sequence, category order, modes, wilds, hole rules, shares.
# Deliberately written without the evaluator's tables or tricks.

FIVE_KIND = 9
STD_RANKS = "23456789TJQKA"
SPEC_NAMES = ["high_card", "pair", "two_pair", "trips", "straight", "flush", "full_house",
              "quads", "straight_flush"]


def _rank_char(c: int) -> str:
    return STD_RANKS[c // 4]


def ref_high_key(cards, ranks_seq: str = STD_RANKS, order=None, wheel: bool = True,
                 straights: bool = True, flushes: bool = True, faces=None) -> tuple:
    """Bigger = better. `faces` overrides card faces (used for wild substitution)."""
    faces = list(faces if faces is not None else cards)
    k = len(faces)
    vals = sorted((ranks_seq.index(_rank_char(c)) for c in faces), reverse=True)
    suits = {c % 4 for c in faces}
    flush = flushes and k >= 3 and len(suits) == 1
    distinct = sorted(set(vals), reverse=True)
    top = None
    if straights and k >= 3 and len(distinct) == k:
        if distinct[0] - distinct[-1] == k - 1:
            top = distinct[0]
        elif wheel and distinct == [len(ranks_seq) - 1] + list(range(k - 2, -1, -1)):
            top = k - 2
    cnt = {v: vals.count(v) for v in distinct}
    by_count = sorted(distinct, key=lambda v: (cnt[v], v), reverse=True)
    grouped = [v for v in by_count for _ in range(cnt[v])]
    if max(cnt.values()) >= 5:
        cat, tie = FIVE_KIND, grouped
    elif top is not None and flush:
        cat, tie = 8, [top]
    elif max(cnt.values()) == 4:
        cat, tie = 7, grouped
    elif sorted(cnt.values(), reverse=True)[:2] == [3, 2]:
        cat, tie = 6, grouped
    elif flush:
        cat, tie = 5, vals
    elif top is not None:
        cat, tie = 4, [top]
    elif max(cnt.values()) == 3:
        cat, tie = 3, grouped
    elif sorted(cnt.values(), reverse=True)[:2] == [2, 2]:
        cat, tie = 2, grouped
    elif max(cnt.values()) == 2:
        cat, tie = 1, grouped
    else:
        cat, tie = 0, vals
    if order is not None and cat != FIVE_KIND:
        cat = order.index(SPEC_NAMES[cat])
    return (cat, *tie)


def ref_low_a5_key(cards, qualifier=None):
    """Ace-to-five low. Bigger = better; None if it doesn't qualify."""
    seq = "A23456789TJQK"
    vals = sorted((seq.index(_rank_char(c)) for c in cards), reverse=True)
    cnt = {v: vals.count(v) for v in set(vals)}
    shape = sorted(cnt.values(), reverse=True)
    cat = {(1, 1, 1, 1, 1): 0, (2, 1, 1, 1): 1, (2, 2, 1): 2, (3, 1, 1): 3, (3, 2): 4,
           (4, 1): 5, (5,): 6}.get(tuple(shape), len(shape))
    by_count = sorted(cnt, key=lambda v: (cnt[v], v), reverse=True)
    grouped = [v for v in by_count for _ in range(cnt[v])]
    if qualifier is not None and (cat != 0 or vals[0] > seq.index(qualifier)):
        return None
    return (-cat, *(-v for v in grouped))


def ref_low_27_key(cards):
    """Deuce-to-seven: the worst high hand (no wheel) wins. Bigger = better."""
    return tuple(-x for x in ref_high_key(cards, wheel=False))


def ref_selections(n_hole, n_board, k, exact=None, lo=None, hi=None):
    """Index tuples of allowed k-card selections under the hole rules."""
    lo_u = exact if exact is not None else (lo or 0)
    hi_u = exact if exact is not None else (hi if hi is not None else k)
    out = []
    for u in range(lo_u, hi_u + 1):
        for h in itertools.combinations(range(n_hole), u):
            for b in itertools.combinations(range(n_hole, n_hole + n_board), k - u):
                out.append(h + b)
    return out


def ref_best_general(hole, board, keyfn, k=5, exact=None, lo=None, hi=None, select=None):
    """Best key over allowed selections; selections of `select` > k cards score as their
    best k-subset. keyfn may return None (non-qualifying)."""
    cards = list(hole) + list(board)
    sel = select or k
    best = None
    for pick in ref_selections(len(hole), len(board), sel, exact, lo, hi):
        for sub in itertools.combinations(pick, k):
            key = keyfn([cards[i] for i in sub])
            if key is not None and (best is None or key > best):
                best = key
    return best


def ref_wild_key(cards, wild_mask, **kw):
    """Best high key with each wild card replaced by every standard face (duplicates allowed)."""
    nat = [c for c, w in zip(cards, wild_mask) if not w]
    n_wild = len(cards) - len(nat)
    best = None
    for fill in itertools.product(range(52), repeat=n_wild):
        key = ref_high_key(None, faces=nat + list(fill), **kw)
        if best is None or key > best:
            best = key
    return best


def ref_shares(keys_per_board_component):
    """keys[board][component][player] -> pot fractions (None = not qualified).
    Hi-lo: if no one qualifies for low, the high takes the low half too."""
    boards = keys_per_board_component
    n = len(boards[0][0])
    out = [0.0] * n
    for comps in boards:
        live = [c for c in comps if any(k is not None for k in c)]
        for comp in live:
            best = max(k for k in comp if k is not None)
            win = [p for p, k in enumerate(comp) if k == best]
            for p in win:
                out[p] += 1.0 / len(boards) / len(live) / len(win)
    return out
