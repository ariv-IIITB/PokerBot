"""Opponent range tracking over the 1326 hole-card combos.

A range is a float vector of weights. Each observed opponent action multiplies
the weights by a likelihood P(action | hand strength) where strength is the
hand's percentile (made hand vs current board, bumped for draws; preflop: the
starting-hand percentile). Updates are blended with the previous range so a
mis-modelled opponent can't collapse our range to nothing.

Discard Hold'em: every player is dealt 3 hole cards and keeps 2. The range is over the
2 cards the opponent will KEEP. Preflop it starts from the distribution of the best
2-card keep of a random 3-card hand (stronger than a random pair), and "percentile"
means the percentile among those best keeps. When the opponent's discard is revealed,
combos that would have kept the discarded card instead are down-weighted.
"""
import numpy as np

from .equity import COMBO_A, COMBO_B, COMBO_ID, N_COMBOS, blocked_mask
from .evaluator import category, evaluate
from .tables import PF_EQ


def _build_preflop():
    ra, rb = COMBO_A % 13, COMBO_B % 13
    suited = (COMBO_A // 13) == (COMBO_B // 13)
    hi, lo = np.maximum(ra, rb), np.minimum(ra, rb)
    eq_table = np.asarray(PF_EQ)
    return np.where((hi == lo) | suited, eq_table[hi, lo], eq_table[lo, hi]), hi, lo, suited


PF_COMBO_EQ, _HI, _LO, _SUITED = _build_preflop()


def _build_keep3():
    """Best 2-card keep of random 3-card hands (offline-style sampling, fixed seed).

    Returns (sorted best-keep equities, prior weight per combo = how often that kind of
    hand is the best keep)."""
    rng = np.random.default_rng(7)
    n = 40000
    hands = np.argpartition(rng.random((n, 52)), 2, axis=1)[:, :3]
    a, b, c = hands[:, 0], hands[:, 1], hands[:, 2]
    ids = np.stack([COMBO_ID[a, b], COMBO_ID[a, c], COMBO_ID[b, c]], axis=1)
    eqs = PF_COMBO_EQ[ids]
    pick = eqs.argmax(1)
    best_id = ids[np.arange(n), pick]
    cls = _HI * 26 + _LO * 2 + _SUITED.astype(np.int64)          # hand class of every combo
    class_n = np.bincount(cls, minlength=13 * 26)
    class_hits = np.bincount(cls[best_id], minlength=13 * 26) + 1.0   # +1: no class gets zero weight
    prior = class_hits[cls] / class_n[cls]
    return np.sort(eqs.max(1)), prior / prior.sum() * N_COMBOS


_KEEP3_SORTED, PF_PRIOR = _build_keep3()


def _pct3(eq):
    """Percentile (0..1) of a keep with preflop equity `eq` among best keeps of 3-card hands."""
    lo = np.searchsorted(_KEEP3_SORTED, eq, side="left")
    hi = np.searchsorted(_KEEP3_SORTED, eq, side="right")
    return (lo + hi) / (2.0 * len(_KEEP3_SORTED))


PF_PCT = _pct3(PF_COMBO_EQ)


def pf_percentile(hole):
    """Percentile (0 worst .. 1 best) of our own starting hand: its best 2-card keep."""
    hole = sorted(hole)
    if len(hole) < 2:
        return 0.5
    best = max(PF_COMBO_EQ[COMBO_ID[x, y]] for i, x in enumerate(hole) for y in hole[i + 1:])
    return float(_pct3(best))


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


_WIN_IDX = [np.arange(j, j + 5) for j in range(10)]


def _draw_flags(cards, sc, nboard):
    """Cheap flush/straight draw detector for (L,k) cards (k=5 or 6; first two are hole)."""
    L = cards.shape[0]
    ranks, suits = cards % 13, cards // 13
    scnt = (suits[:, :, None] == np.arange(4)).sum(1)               # (L,4)
    ar = np.arange(L)
    fd = (scnt[ar, suits[:, 0]] == 4) | (scnt[ar, suits[:, 1]] == 4)
    pres = (ranks[:, :, None] == np.arange(13)).any(1)
    ext = np.concatenate([pres[:, 12:13], pres], axis=1)
    wsum = np.stack([ext[:, j:j + 5].sum(1) for j in range(10)], axis=1)
    bpres = pres.copy()
    # board-only presence: recompute from board cards (cols 2..)
    bp = (ranks[:, 2:, None] == np.arange(13)).any(1)
    bext = np.concatenate([bp[:, 12:13], bp], axis=1)
    bsum = np.stack([bext[:, j:j + 5].sum(1) for j in range(10)], axis=1)
    sd = ((wsum == 4) & (bsum < 4)).any(1) & (category(sc) < 4)
    del bpres
    return fd | sd


class BoardInfo:
    __slots__ = ("live", "inv", "nu", "draw")

    def __init__(self, board):
        board = tuple(board)
        blk = blocked_mask(board)
        live = np.nonzero(~blk)[0]
        b = np.broadcast_to(np.asarray(board, dtype=np.int64), (len(live), len(board)))
        cards = np.concatenate([COMBO_A[live][:, None], COMBO_B[live][:, None], b], axis=1)
        sc = evaluate(cards)
        uniq, inv = np.unique(sc, return_inverse=True)
        self.live, self.inv, self.nu = live, inv, len(uniq)
        if len(board) in (3, 4):
            self.draw = _draw_flags(cards, sc, len(board))
        else:
            self.draw = None


class RangeTracker:
    """Holds the opponent's weight vector for the current hand."""

    def __init__(self):
        self.w = PF_PRIOR.copy()
        self._cache = {}

    def reset(self, hole):
        self.w = PF_PRIOR * (~blocked_mask(hole))
        self._cache = {}

    def block(self, cards):
        self.w = np.where(blocked_mask(cards), 0.0, self.w)

    def info(self, board):
        key = tuple(board)
        bi = self._cache.get(key)
        if bi is None:
            bi = BoardInfo(board)
            self._cache[key] = bi
        return bi

    def strength(self, board):
        """Per-combo strength percentile in [0,1] against `board` under the current weights."""
        if len(board) == 0:
            return PF_PCT
        bi = self.info(board)
        wl = self.w[bi.live]
        tot = wl.sum()
        s = np.full(N_COMBOS, 0.5)
        if tot <= 0:
            return s
        ws = np.bincount(bi.inv, weights=wl, minlength=bi.nu)
        cum = np.cumsum(ws) - ws
        pu = ((cum + 0.5 * ws) / tot)[bi.inv]
        if bi.draw is not None:
            pu = np.where(bi.draw & (pu < 0.6), 0.6, pu)
        s[bi.live] = np.clip(pu, 0.0, 1.0)
        return s

    def update(self, kind, board, opp, f=0.5, level=2):
        """Apply an opponent action to the range.

        Preflop kinds: open, limp, iso, pf_check, pf_call, pf_call3, pf_reraise (level)
        Postflop kinds: bet, raise, call, check  (f = bet size / pot before the bet)
        """
        s = self.strength(board)
        if len(board) == 0:
            like = _preflop_like(kind, s, opp, level)
        else:
            like = _postflop_like(kind, s, opp, f)
        if like is not None:
            self._blend(like)

    def _blend(self, like):
        new = self.w * like
        tn = new.sum()
        if tn <= 1e-12:
            return
        old_n = self.w / self.w.sum()
        self.w = 0.92 * new / tn + 0.08 * old_n

    def apply_discard(self, board, card):
        """The opponent discarded `card` after seeing `board` (the flop).

        A player keeps the best two of three cards, so a combo (a, b) is less likely if
        (a, card) or (b, card) would have been the stronger hand on this board."""
        if len(board) < 3:
            return
        self.block([card])
        s = self.strength(board)
        live = np.nonzero(self.w > 0)[0]
        if len(live) == 0:
            return
        a, b = COMBO_A[live], COMBO_B[live]
        alt = np.maximum(s[COMBO_ID[a, card]], s[COMBO_ID[b, card]])
        like = np.ones(N_COMBOS)
        like[live] = 0.15 + 0.85 * _sig((s[live] - alt) / 0.06)
        self._blend(like)


def _preflop_like(kind, s, opp, level):
    if kind == "open":
        cut = 1.0 - opp.pf_open.value
        return _sig((s - cut) / 0.05) + 0.01
    if kind == "limp":
        cut = 1.0 - opp.pf_open.value
        return 0.12 + 0.88 * _sig((cut - s) / 0.08)
    if kind == "iso":
        return _sig((s - 0.60) / 0.05) + 0.03
    if kind == "pf_check":
        return 0.35 + 0.65 * _sig((0.70 - s) / 0.08)
    if kind == "pf_call":
        dc = 1.0 - opp.pf_defend.value
        c3 = 1.0 - opp.pf_3bet.value
        return _sig((s - dc) / 0.05) * (1.0 - _sig((s - c3) / 0.04)) + 0.02
    if kind == "pf_call3":
        return _sig((s - 0.50) / 0.08) * (1.0 - _sig((s - 0.95) / 0.02)) + 0.02
    if kind == "pf_reraise":
        cut = 1.0 - opp.pf_3bet.value if level <= 2 else 0.94
        return _sig((s - cut) / 0.03) + 0.01
    return None


def _postflop_like(kind, s, opp, f):
    f = min(max(f, 0.05), 3.0)
    if kind in ("bet", "raise"):
        k = (1.5 + 2.0 * f) * opp.agg_scale()
        return s ** k + opp.bluff_mass() * (s < 0.35)
    if kind == "call":
        return 0.05 + (s ** (0.7 + 1.5 * f)) * (1.0 - 0.5 * s ** 5)
    if kind == "check":
        return 0.25 + (1.0 - s) ** 1.2
    return None
