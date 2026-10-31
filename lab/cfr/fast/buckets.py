"""Numba twin of bot/abstraction.py's v2 bucket features (docs/cfr/ABSTRACTION_V1.md section 5).

Same SplitMix64 sampler, same draw order, same integer counts: the features (and so the bucket
ids) are bit-identical to the runtime's. tests/test_cfr_buckets.py holds them equal.
"""
from __future__ import annotations

import numpy as np
from numba import njit

from bot.abstraction import FLOP_OPP, FLOP_RUNOUTS, GOLDEN, MIX1, MIX2, SEED_BASE, SEPARATOR, TURN_OPP
from lab.cfr.fast.eval7 import TABLES, eval7

U_GOLDEN = np.uint64(GOLDEN)
U_MIX1 = np.uint64(MIX1)
U_MIX2 = np.uint64(MIX2)
U30, U27, U31 = np.uint64(30), np.uint64(27), np.uint64(31)


@njit(cache=True, inline="always")
def mix(z):
    z = (z ^ (z >> U30)) * U_MIX1
    z = (z ^ (z >> U27)) * U_MIX2
    return z ^ (z >> U31)


@njit(cache=True)
def _absorb(s, c):
    return mix((s ^ np.uint64(c)) + U_GOLDEN)


@njit(cache=True)
def card_seed(street, hole, board, dead):
    """Inputs sorted ascending (int64 arrays)."""
    s = np.uint64(SEED_BASE + street)
    for c in hole:
        s = _absorb(s, c)
    s = _absorb(s, SEPARATOR)
    for c in board:
        s = _absorb(s, c)
    s = _absorb(s, SEPARATOR)
    for c in dead:
        s = _absorb(s, c)
    return s


@njit(cache=True, inline="always")
def _draw(state, m):
    """(new state, index in [0, m))."""
    state = state + U_GOLDEN
    return state, np.int64(mix(state) % np.uint64(m))


@njit(cache=True)
def stream(seed, n):
    """The first n SplitMix64 outputs from state `seed` (for tests)."""
    out = np.empty(n, dtype=np.uint64)
    state = np.uint64(seed)
    for k in range(n):
        state = state + U_GOLDEN
        out[k] = mix(state)
    return out


@njit(cache=True, inline="always")
def _pair(state, m):
    state, i = _draw(state, m)
    state, j = _draw(state, m - 1)
    if j >= i:
        j += 1
    return state, i, j


@njit(cache=True)
def _unseen(known):
    mask = np.ones(52, dtype=np.bool_)
    for c in known:
        mask[c] = False
    return np.nonzero(mask)[0].astype(np.int64)


@njit(cache=True)
def flop_counts(hole, board, comb5, flush5, comb7, multi7):
    """(best keep, sum of counts, sum of squared counts) for sorted hole (3) and board (3)."""
    scratch = np.empty(8, dtype=np.int64)
    R, O = FLOP_RUNOUTS, FLOP_OPP
    known = np.concatenate((hole, board))
    unseen = _unseen(known)
    m = unseen.shape[0]
    state = card_seed(1, hole, np.sort(board), np.empty(0, dtype=np.int64))
    s1 = np.zeros(3, dtype=np.int64)
    s2 = np.zeros(3, dtype=np.int64)
    keeps = np.array([[0, 1], [0, 2], [1, 2]], dtype=np.int64)
    mine = np.empty((3, 7), dtype=np.int64)
    opp = np.empty(7, dtype=np.int64)
    for r in range(R):
        state, i, j = _pair(state, m)
        lo, hi = min(i, j), max(i, j)
        for k in range(3):
            mine[k, 0] = hole[keeps[k, 0]]
            mine[k, 1] = hole[keeps[k, 1]]
            mine[k, 2:5] = board
            mine[k, 5] = unseen[i]
            mine[k, 6] = unseen[j]
        opp[2:5] = board
        opp[5] = unseen[i]
        opp[6] = unseen[j]
        vm = np.empty(3, dtype=np.int64)
        for k in range(3):
            vm[k] = eval7(mine[k], comb5, flush5, comb7, multi7, scratch)
        cnt = np.zeros(3, dtype=np.int64)
        for _o in range(O):
            state, a, b = _pair(state, m - 2)
            if a >= lo:
                a += 1
            if a >= hi:
                a += 1
            if b >= lo:
                b += 1
            if b >= hi:
                b += 1
            opp[0] = unseen[a]
            opp[1] = unseen[b]
            vo = eval7(opp, comb5, flush5, comb7, multi7, scratch)
            for k in range(3):
                cnt[k] += 2 if vm[k] > vo else (1 if vm[k] == vo else 0)
        for k in range(3):
            s1[k] += cnt[k]
            s2[k] += cnt[k] * cnt[k]
    best = 0
    for k in range(1, 3):
        if s1[k] > s1[best]:
            best = k
    return best, s1[best], s2[best]


@njit(cache=True)
def turn_counts(hole, board, dead, comb5, flush5, comb7, multi7):
    """(sum of counts, sum of squared counts, number of rivers) for sorted hole (2), board (4), dead."""
    scratch = np.empty(8, dtype=np.int64)
    O = TURN_OPP
    unseen = _unseen(np.concatenate((hole, board, dead)))
    m = unseen.shape[0]
    state = card_seed(2, hole, np.sort(board), np.sort(dead))
    mine = np.empty(7, dtype=np.int64)
    opp = np.empty(7, dtype=np.int64)
    mine[0], mine[1] = hole[0], hole[1]
    mine[2:6] = board
    opp[2:6] = board
    s1 = 0
    s2 = 0
    for r in range(m):
        mine[6] = unseen[r]
        opp[6] = unseen[r]
        vm = eval7(mine, comb5, flush5, comb7, multi7, scratch)
        cnt = 0
        for _o in range(O):
            state, a, b = _pair(state, m - 1)
            if a >= r:
                a += 1
            if b >= r:
                b += 1
            opp[0] = unseen[a]
            opp[1] = unseen[b]
            vo = eval7(opp, comb5, flush5, comb7, multi7, scratch)
            cnt += 2 if vm > vo else (1 if vm == vo else 0)
        s1 += cnt
        s2 += cnt * cnt
    return s1, s2, m


@njit(cache=True)
def river_counts(hole, board, dead, comb5, flush5, comb7, multi7):
    """(sum of counts, number of opponent hands, blocker bit)."""
    scratch = np.empty(8, dtype=np.int64)
    unseen = _unseen(np.concatenate((hole, board, dead)))
    m = unseen.shape[0]
    mine = np.empty(7, dtype=np.int64)
    opp = np.empty(7, dtype=np.int64)
    mine[0], mine[1] = hole[0], hole[1]
    mine[2:7] = board
    opp[2:7] = board
    vm = eval7(mine, comb5, flush5, comb7, multi7, scratch)
    s = 0
    n = 0
    for x in range(m):
        for y in range(x + 1, m):
            opp[0] = unseen[x]
            opp[1] = unseen[y]
            vo = eval7(opp, comb5, flush5, comb7, multi7, scratch)
            s += 2 if vm > vo else (1 if vm == vo else 0)
            n += 1
    suits = np.zeros(4, dtype=np.int64)
    for c in board:
        suits[c & 3] += 1
    blocker = 1 if (suits[hole[0] & 3] >= 3 or suits[hole[1] & 3] >= 3) else 0
    return s, n, blocker


# ---- Python-facing wrappers (same return values as bot.abstraction's functions)

def _arr(cards) -> np.ndarray:
    return np.array(sorted(int(c) for c in cards), dtype=np.int64)


def flop_features(hole3, board3) -> tuple[int, float, float]:
    k, s1, s2 = flop_counts(_arr(hole3), np.array([int(c) for c in board3], dtype=np.int64),
                            *TABLES)
    R, O = FLOP_RUNOUTS, FLOP_OPP
    return int(k), int(s1) / (2 * O * R), int(s2) / ((2 * O) ** 2 * R)


def turn_features(hole2, board4, dead) -> tuple[float, float]:
    s1, s2, m = turn_counts(_arr(hole2), np.array([int(c) for c in board4], dtype=np.int64),
                            _arr(dead), *TABLES)
    O = TURN_OPP
    return int(s1) / (2 * O * m), int(s2) / ((2 * O) ** 2 * m)


def river_features(hole2, board5, dead) -> tuple[float, int]:
    s, n, blocker = river_counts(_arr(hole2), np.array([int(c) for c in board5], dtype=np.int64),
                                 _arr(dead), *TABLES)
    return int(s) / (2 * int(n)), int(blocker)
