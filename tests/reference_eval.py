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
