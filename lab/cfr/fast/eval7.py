"""7-card hand evaluator for the fast CFR trainer (Numba; lab only).

The values are exactly bot/evaluator.py's (standard high hands): they come from the same 5-card
score tables (indexed by the sorted rank multiset, one for flushes, one not).

  MULTI7[idx7(ranks)]  best non-flush score over the 21 five-card subsets of 7 ranks (precomputed
                       once from the 5-card table: 50,388 multisets)
  flush                if a suit has 5+ cards, the best flush-table score over that suit's 5-subsets
  value                max of the two (quads and full houses can beat a flush; MULTI7 covers them)

Cards are bot.cards ids 0..51 (rank = id // 4, suit = id % 4).
"""
from __future__ import annotations

import itertools
from math import comb

import numpy as np
from numba import njit

from bot.evaluator import RankRules, tables_for


def _tables():
    t = tables_for(RankRules(k=5))
    comb5 = np.ascontiguousarray(t.comb_np, dtype=np.int64)
    multi5 = np.ascontiguousarray(t.multi_np, dtype=np.int64)
    flush5 = np.ascontiguousarray(t.flush_np, dtype=np.int64)
    comb7 = np.array([[comb(n, j) for j in range(8)] for n in range(13 + 7)], dtype=np.int64)
    ms = np.array(list(itertools.combinations_with_replacement(range(13), 7)), dtype=np.int64)
    idx7 = sum(comb7[ms[:, i] + i, i + 1] for i in range(7))
    best = np.full(len(ms), -1, dtype=np.int64)
    for sub in itertools.combinations(range(7), 5):
        r = ms[:, sub]                                   # sorted, since ms rows are sorted
        idx5 = sum(comb5[r[:, i] + i, i + 1] for i in range(5))
        best = np.maximum(best, multi5[idx5])
    multi7 = np.full(comb(13 + 7 - 1, 7), -1, dtype=np.int64)
    multi7[idx7] = best
    return comb5, multi5, flush5, comb7, multi7


COMB5, MULTI5, FLUSH5, COMB7, MULTI7 = _tables()
SUBSETS5 = np.array(list(itertools.combinations(range(7), 5)), dtype=np.int64)    # for flushes
TABLES = (COMB5, FLUSH5, COMB7, MULTI7)


@njit(cache=True)
def eval7(cards, comb5, flush5, comb7, multi7, scratch) -> int:
    """Best 5-card score from 7 cards. `scratch`: an int64 array of length >= 7 (reused)."""
    s0 = s1 = s2 = s3 = 0
    for i in range(7):                        # ranks, insertion-sorted into scratch
        c = cards[i]
        x = c >> 2
        j = i - 1
        while j >= 0 and scratch[j] > x:
            scratch[j + 1] = scratch[j]
            j -= 1
        scratch[j + 1] = x
        s = c & 3
        if s == 0:
            s0 += 1
        elif s == 1:
            s1 += 1
        elif s == 2:
            s2 += 1
        else:
            s3 += 1
    idx = 0
    for i in range(7):
        idx += comb7[scratch[i] + i, i + 1]
    best = multi7[idx]
    fs = -1
    if s0 >= 5:
        fs = 0
    elif s1 >= 5:
        fs = 1
    elif s2 >= 5:
        fs = 2
    elif s3 >= 5:
        fs = 3
    if fs >= 0:                               # rare: score the flush suit's 5-card subsets
        n = 0
        for i in range(7):
            if (cards[i] & 3) == fs:
                scratch[n] = cards[i] >> 2
                n += 1
        for a in range(n):
            for b in range(a + 1, n):
                for c in range(b + 1, n):
                    for d in range(c + 1, n):
                        for e in range(d + 1, n):
                            r0, r1, r2, r3, r4 = scratch[a], scratch[b], scratch[c], scratch[d], scratch[e]
                            # sort 5 values (network)
                            if r0 > r1:
                                r0, r1 = r1, r0
                            if r3 > r4:
                                r3, r4 = r4, r3
                            if r2 > r4:
                                r2, r4 = r4, r2
                            if r2 > r3:
                                r2, r3 = r3, r2
                            if r0 > r3:
                                r0, r3 = r3, r0
                            if r0 > r2:
                                r0, r2 = r2, r0
                            if r1 > r4:
                                r1, r4 = r4, r1
                            if r1 > r3:
                                r1, r3 = r3, r1
                            if r1 > r2:
                                r1, r2 = r2, r1
                            i5 = (comb5[r0, 1] + comb5[r1 + 1, 2] + comb5[r2 + 2, 3]
                                  + comb5[r3 + 3, 4] + comb5[r4 + 4, 5])
                            v = flush5[i5]
                            if v > best:
                                best = v
    return best


@njit(cache=True)
def eval7_batch(hands, comb5, flush5, comb7, multi7):
    """Scores of an (n, 7) array of hands."""
    out = np.empty(hands.shape[0], dtype=np.int64)
    scratch = np.empty(8, dtype=np.int64)
    for i in range(hands.shape[0]):
        out[i] = eval7(hands[i], comb5, flush5, comb7, multi7, scratch)
    return out


def evaluate7(hands: np.ndarray) -> np.ndarray:
    """Convenience wrapper with the module's tables."""
    return eval7_batch(np.ascontiguousarray(hands, dtype=np.int64), *TABLES)
