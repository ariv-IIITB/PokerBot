"""Monte-Carlo equity of our hand against a weighted opponent range (NumPy only).

Discard Hold'em: before the discard we hold 3 hole cards and will keep 2 of them, so a
3-card hand is valued as its best 2-card keep. Discarded cards (ours and the opponent's)
are out of play: they never come back on the board and the opponent cannot hold them.
"""
from itertools import combinations

import numpy as np

from .evaluator import evaluate

# All 1326 two-card combos, ordered by (a, b) with a < b.
_A, _B = np.triu_indices(52, k=1)
COMBO_A = _A.astype(np.int64)
COMBO_B = _B.astype(np.int64)
N_COMBOS = len(COMBO_A)
# combo id lookup: COMBO_ID[a, b] for a < b
COMBO_ID = np.full((52, 52), -1, dtype=np.int64)
COMBO_ID[COMBO_A, COMBO_B] = np.arange(N_COMBOS)
COMBO_ID[COMBO_B, COMBO_A] = np.arange(N_COMBOS)


def blocked_mask(cards):
    """Boolean (1326,) True for combos that contain any of `cards`."""
    m = np.zeros(N_COMBOS, dtype=bool)
    for c in cards:
        m |= (COMBO_A == c) | (COMBO_B == c)
    return m


def keeps(hole):
    """The 2-card hands we can end up with: the hole itself, or each pair out of 3 cards."""
    hole = tuple(hole)
    if len(hole) <= 2:
        return [hole]
    return list(combinations(hole, 2))


def _sample(hole, board, weights, n, rng, dead):
    """Opponent combos drawn from the range and a runout for each, avoiding every known card.

    Returns (oa, ob, full): opponent cards (n,) each and the completed board (n, 5)."""
    known = list(hole) + list(board) + list(dead)
    blk = blocked_mask(known)
    if weights is None:
        w = (~blk).astype(np.float64)
    else:
        w = np.where(blk, 0.0, weights)
    tot = w.sum()
    if tot <= 0:                       # degenerate range -> fall back to uniform
        w = (~blk).astype(np.float64)
        tot = w.sum()
    cdf = np.cumsum(w) / tot
    idx = np.searchsorted(cdf, rng.random(n), side="right")
    np.clip(idx, 0, N_COMBOS - 1, out=idx)
    oa, ob = COMBO_A[idx], COMBO_B[idx]

    need = 5 - len(board)
    ar = np.arange(n)
    if need > 0:
        keys = rng.random((n, 52))
        keys[:, known] = 2.0
        keys[ar, oa] = 2.0
        keys[ar, ob] = 2.0
        run = np.argpartition(keys, need - 1, axis=1)[:, :need]
        full = np.concatenate([np.broadcast_to(np.asarray(board, dtype=np.int64), (n, len(board))), run], axis=1)
    else:
        full = np.broadcast_to(np.asarray(board, dtype=np.int64), (n, 5))
    return oa, ob, full


def keep_scores(options, oa, ob, full):
    """Per-sample win (1), tie (0.5) or loss (0) for each 2-card option on the sampled runouts."""
    n = len(oa)
    opp = np.concatenate([oa[:, None], ob[:, None], full], axis=1)
    os_ = evaluate(opp)
    out = []
    for keep in options:
        hero = np.concatenate([np.broadcast_to(np.asarray(keep, dtype=np.int64), (n, 2)), full], axis=1)
        hs = evaluate(hero)
        out.append((hs > os_) + 0.5 * (hs == os_))
    return out


def keep_equities(hole, board, weights, n, rng, dead=()):
    """Equity of each 2-card keep of `hole` (one entry if we already hold 2 cards).

    All options are scored on the same sampled opponent hands and runouts, so their
    differences are low-noise. Returns (options, [equity per option])."""
    options = keeps(hole)
    oa, ob, full = _sample(hole, board, weights, n, rng, dead)
    res = keep_scores(options, oa, ob, full)
    return options, [float(r.mean()) for r in res]


def equity(hole, board, weights, n, rng, dead=()):
    """Equity of `hole` vs a range given as (1326,) non-negative weights.

    weights=None means uniform over all unblocked combos. Blocked and dead combos are
    ignored automatically. With 3 hole cards the value is that of the best 2-card keep: the
    keep is picked on one half of the samples and measured on the other, so choosing the
    maximum does not inflate the estimate. Returns (equity, standard_error).
    """
    options = keeps(hole)
    oa, ob, full = _sample(hole, board, weights, n, rng, dead)
    res = keep_scores(options, oa, ob, full)
    if len(options) == 1:
        r = res[0]
    else:
        h = n // 2
        best = int(np.argmax([x[:h].mean() for x in res]))
        r = res[best][h:]
    return float(r.mean()), float(r.std() / np.sqrt(len(r)))
