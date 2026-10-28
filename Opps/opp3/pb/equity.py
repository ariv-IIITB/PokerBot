"""Monte-Carlo equity of our hand against a weighted opponent range (NumPy only)."""
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


def equity(hole, board, weights, n, rng):
    """Equity of `hole` vs a range given as (1326,) non-negative weights.

    weights=None means uniform over all unblocked combos. Blocked combos are
    ignored automatically. Returns (equity, standard_error).
    """
    known = list(hole) + list(board)
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
        keys[:, list(known)] = 2.0
        keys[ar, oa] = 2.0
        keys[ar, ob] = 2.0
        run = np.argpartition(keys, need - 1, axis=1)[:, :need]
        full = np.concatenate([np.broadcast_to(np.asarray(board, dtype=np.int64), (n, len(board))), run], axis=1)
    else:
        full = np.broadcast_to(np.asarray(board, dtype=np.int64), (n, 5))
    hero = np.concatenate([np.broadcast_to(np.asarray(hole, dtype=np.int64), (n, 2)), full], axis=1)
    opp = np.concatenate([oa[:, None], ob[:, None], full], axis=1)
    hs, os_ = evaluate(hero), evaluate(opp)
    res = (hs > os_) + 0.5 * (hs == os_)
    e = float(res.mean())
    se = float(res.std() / np.sqrt(n))
    return e, se
