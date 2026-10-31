"""Discard Hold'em preflop helper: strength of a 3-card hand = its best 2-card keep.

The preflop charts of the original bot are defined for 2-card hands. With 3 hole cards each
chart is applied by frequency: a hand is "in the chart" when the percentile of its best keep,
among the best keeps of random 3-card hands, is inside the share of starting hands the chart
contains. Same opening / defending frequencies as the original, now for 3-card hands.
"""
import bisect
import random

from tables import PF_EQ

RANKS = 13


def keep_equity(c1, c2):
    """Preflop equity vs a random hand of the 2-card hand (c1, c2); cards are rank << 2 | suit."""
    r1, r2 = c1 >> 2, c2 >> 2
    hi, lo = max(r1, r2), min(r1, r2)
    if hi == lo or (c1 & 3) == (c2 & 3):
        return PF_EQ[hi][lo]
    return PF_EQ[lo][hi]


def best_keep_equity(cards):
    cards = list(cards)
    best = 0.0
    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            best = max(best, keep_equity(cards[i], cards[j]))
    return best


def _build():
    rng = random.Random(12345)
    deck = list(range(52))
    vals = []
    for _ in range(20000):
        a, b, c = rng.sample(deck, 3)
        vals.append(max(keep_equity(a, b), keep_equity(a, c), keep_equity(b, c)))
    vals.sort()
    return vals


_SORTED = _build()


def percentile(cards):
    """0 (worst) .. 1 (best): rank of this hand's best keep among 3-card hands."""
    v = best_keep_equity(cards)
    lo = bisect.bisect_left(_SORTED, v)
    hi = bisect.bisect_right(_SORTED, v)
    return (lo + hi) / (2.0 * len(_SORTED))
