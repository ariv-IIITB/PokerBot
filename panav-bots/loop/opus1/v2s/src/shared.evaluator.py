"""Numpy hand evaluator (BUILDMAP §4.4, Appendix A).

Hand value v = (cat << 26) | (A << 13) | B as int64; higher wins, equal splits.
`cat` follows the engine's HAND_NAMES order (0 high card .. 8 straight flush).
"""
import numpy as np

# ---------------------------------------------------------------- 8192-entry tables
_M = 1 << 13
BITS = (1 << np.arange(13)).astype(np.int64)
_m = np.arange(_M, dtype=np.int64)
_bits = (_m[:, None] >> np.arange(13)) & 1                   # (_M, 13)
POP = _bits.sum(axis=1)
_from_top = np.cumsum(_bits[:, ::-1], axis=1)[:, ::-1]       # set bits at or above each rank
TOP = {k: ((_bits * (_from_top <= k)) * BITS).sum(axis=1) for k in (1, 2, 3, 5)}
ST = np.full(_M, -1, np.int64)                               # top rank of best straight, or -1
for _t in range(4, 13):
    _w = 0b11111 << (_t - 4)
    ST[(_m & _w) == _w] = _t
_wheel = (1 << 12) | 0b1111
ST[((_m & _wheel) == _wheel) & (ST < 0)] = 3


def _value(cat, a, b):
    return (np.int64(cat) << 26) | (a << 13) | b


def _finish(rc, sm, rows):
    """rc: (N,13) rank counts; sm: (N,4) per-suit rank masks."""
    ranks = (rc > 0).astype(np.int64) @ BITS
    m2 = (rc >= 2).astype(np.int64) @ BITS
    m3 = (rc >= 3).astype(np.int64) @ BITS
    m4 = (rc >= 4).astype(np.int64) @ BITS
    sc = POP[sm]
    fs = sc.argmax(axis=1)
    has_flush = sc[rows, fs] >= 5
    fmask = np.where(has_flush, sm[rows, fs], 0)
    sf = np.where(has_flush, ST[fmask], -1)
    st = ST[ranks]
    q = TOP[1][m4]; t = TOP[1][m3]; fh_pair = TOP[1][m2 & ~t]; tp = TOP[2][m2]; one = np.int64(1)
    conds = [sf >= 0, m4 > 0, (m3 > 0) & (fh_pair > 0), has_flush, st >= 0, m3 > 0, POP[m2] >= 2, m2 > 0]
    vals = [_value(8, one << np.maximum(sf, 0), 0),
            _value(7, q, TOP[1][ranks & ~q]),
            _value(6, t, fh_pair),
            _value(5, TOP[5][fmask], 0),
            _value(4, one << np.maximum(st, 0), 0),
            _value(3, t, TOP[2][ranks & ~t]),
            _value(2, tp, TOP[1][ranks & ~tp]),
            _value(1, m2, TOP[3][ranks & ~m2])]
    return np.select(conds, vals, _value(0, TOP[5][ranks], 0))


def evaluate(cards):
    """cards: int array (N, k) with 5 <= k <= 7. Returns int64 hand values (§4.4)."""
    cards = np.asarray(cards, dtype=np.int64)
    N = cards.shape[0]; rows = np.arange(N)
    rc = np.zeros((N, 13), np.int8); sm = np.zeros((N, 4), np.int64)
    for j in range(cards.shape[1]):
        r = cards[:, j] >> 2; s = cards[:, j] & 3
        rc[rows, r] += 1; sm[rows, s] |= (np.int64(1) << r)
    return _finish(rc, sm, rows)


def evaluate_board_plus(board, extra):
    """Fixed board cards + per-row extra cards (N, j). Same values as evaluate()."""
    extra = np.asarray(extra, dtype=np.int64)
    N = extra.shape[0]; rows = np.arange(N)
    brc = np.zeros(13, np.int8); bsm = np.zeros(4, np.int64)
    for c in board:
        c = int(c)
        brc[c >> 2] += 1; bsm[c & 3] |= 1 << (c >> 2)
    rc = np.tile(brc, (N, 1)); sm = np.tile(bsm, (N, 1))
    for j in range(extra.shape[1]):
        r = extra[:, j] >> 2; s = extra[:, j] & 3
        rc[rows, r] += 1; sm[rows, s] |= (np.int64(1) << r)
    return _finish(rc, sm, rows)
