"""Vectorised poker hand evaluator (NumPy only).

evaluate(cards) takes an int array of shape (N, k), k in 5..7, card = suit*13+rank,
and returns an int64 score array of shape (N,). Higher score = better hand; equal
score = exact tie. Score layout: category * 14**5 + five base-14 tie-break slots.

Categories: 0 high card, 1 pair, 2 two pair, 3 trips, 4 straight, 5 flush,
6 full house, 7 quads, 8 straight flush.
"""
import numpy as np

_IDX = np.arange(13, dtype=np.int64)
_W1 = _IDX + 1                       # rank + 1 (0 means "none")
_SIDX = np.arange(4, dtype=np.int64)
_B = 14
_B5 = _B ** 5
_POW = np.array([_B ** 4, _B ** 3, _B ** 2, _B, 1], dtype=np.int64)


def _topk(w, k):
    """w: (N,13) of rank+1 or 0. Returns (N,k) highest values descending (0 if absent)."""
    w = w.copy()
    n = w.shape[0]
    ar = np.arange(n)
    out = np.zeros((n, k), dtype=np.int64)
    for i in range(k):
        pos = w.argmax(1)
        out[:, i] = w[ar, pos]
        w[ar, pos] = 0
    return out


def _straight_high(pres):
    """pres: (N,13) bool rank presence. Returns (N,) rank+1 of the straight's high card, else 0."""
    ext = np.concatenate([pres[:, 12:13], pres], axis=1)          # ace also plays low
    win = np.stack([ext[:, j:j + 5].all(1) for j in range(10)], axis=1)
    has = win.any(1)
    j = 9 - win[:, ::-1].argmax(1)
    return np.where(has, j + 4, 0)


def _slots(n, *cols):
    out = np.zeros((n, 5), dtype=np.int64)
    for i, c in enumerate(cols):
        out[:, i] = c
    return out


def evaluate(cards):
    cards = np.asarray(cards, dtype=np.int64)
    if cards.ndim == 1:
        cards = cards[None, :]
    n = cards.shape[0]
    ranks = cards % 13
    suits = cards // 13
    roh = ranks[:, :, None] == _IDX                      # (N,k,13)
    cnt = roh.sum(1)                                     # (N,13)
    scnt = (suits[:, :, None] == _SIDX).sum(1)           # (N,4)
    anyr = cnt > 0

    # flush / straight flush
    fs = scnt.argmax(1)
    isf = scnt.max(1) >= 5
    fmask = (roh & (suits == fs[:, None])[:, :, None]).any(1) & isf[:, None]
    sf_high = _straight_high(fmask)
    fl5 = _topk(fmask * _W1, 5)

    st_high = _straight_high(anyr)

    quad = cnt == 4
    q1 = (quad * _W1).max(1)
    trips = _topk((cnt == 3) * _W1, 2)
    t1, t2 = trips[:, 0], trips[:, 1]
    prs = _topk((cnt == 2) * _W1, 3)
    p1, p2 = prs[:, 0], prs[:, 1]

    base = _W1 * anyr                                    # present ranks as rank+1
    high5 = _topk(base, 5)

    cat = np.zeros(n, dtype=np.int64)
    slots = high5

    def setc(cond, c, s):
        nonlocal cat, slots
        cat = np.where(cond, c, cat)
        slots = np.where(cond[:, None], s, slots)

    # one pair
    k = _topk(np.where(_W1 == p1[:, None], 0, base), 3)
    setc(p1 > 0, 1, _slots(n, p1, k[:, 0], k[:, 1], k[:, 2]))
    # two pair
    k = _topk(np.where((_W1 == p1[:, None]) | (_W1 == p2[:, None]), 0, base), 1)
    setc((p1 > 0) & (p2 > 0), 2, _slots(n, p1, p2, k[:, 0]))
    # trips
    k = _topk(np.where(_W1 == t1[:, None], 0, base), 2)
    setc(t1 > 0, 3, _slots(n, t1, k[:, 0], k[:, 1]))
    # straight
    setc(st_high > 0, 4, _slots(n, st_high))
    # flush
    setc(isf, 5, fl5)
    # full house
    fhp = np.maximum(t2, p1)
    setc((t1 > 0) & (fhp > 0), 6, _slots(n, t1, fhp))
    # quads
    k = _topk(np.where(_W1 == q1[:, None], 0, base), 1)
    setc(q1 > 0, 7, _slots(n, q1, k[:, 0]))
    # straight flush
    setc(sf_high > 0, 8, _slots(n, sf_high))

    return cat * _B5 + (slots * _POW).sum(1)


def category(score):
    return np.asarray(score) // _B5


def evaluate_one(cards):
    """Scalar convenience wrapper (slow; for tests/tools)."""
    return int(evaluate(np.asarray(cards, dtype=np.int64)[None, :])[0])
