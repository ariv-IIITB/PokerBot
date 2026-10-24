"""Hand evaluators: best `hand_size`-card hand from hole + board, for many rule sets.

How it works
------------
Cards are mapped to (rank position, suit) through the deck's lookup arrays (positions
follow the deck's own rank order, so short-deck straights work automatically). A k-card
hand (k <= 5) is then scored from small tables indexed by its sorted rank multiset
(13 ranks, 5 cards -> 6188 entries): one table for non-flush hands, one for flushes.
With wild cards there is one table pair per number of wilds w, holding the best score
over every way of filling the w wilds (built lazily, once).
The best hand from N cards is the max over the allowed k-card combinations (optionally
"exactly / at least / at most x hole cards"). `evaluate_batch` does it all in NumPy.

Modes:
  high     standard poker ranking (category order configurable)
  low_27   deuce-to-seven lowball: the WORST high hand wins (ace high, straights and
           flushes count, no wheel)
  low_a5   ace-to-five lowball: ace low, straights and flushes ignored; optional
           qualifier ("8 or better": no pair and top card <= 8)

Values are ints, higher always wins, equal = split; -1 = does not qualify (low only).
High layout: category << 20 | rank positions packed 4 bits each, most important first.
Inputs are not checked for duplicate cards (that's the caller's job, for speed).
"""
from __future__ import annotations

import itertools
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from math import comb
from typing import Optional, Sequence

import numpy as np

HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH, FIVE_KIND = range(10)
CATEGORY_NAMES = ("high card", "pair", "two pair", "trips", "straight", "flush",
                  "full house", "quads", "straight flush", "five of a kind")
SPEC_CATEGORY_NAMES = ("high_card", "pair", "two_pair", "trips", "straight", "flush",
                       "full_house", "quads", "straight_flush")
NATURAL_ORDER = tuple(range(10))
CATEGORY_SHIFT = 20
MAX_HAND_SIZE = 5
LOW_BASE = 10 << CATEGORY_SHIFT          # low value = LOW_BASE - high-style value
NOT_QUALIFIED = -1


def category(value: int) -> int:
    """Hand category (HIGH_CARD..FIVE_KIND, after any re-ordering) of a high value."""
    return int(value) >> CATEGORY_SHIFT


def order_from_names(names: Optional[Sequence[str]]) -> tuple[int, ...]:
    """Spec category_order (names, low to high) -> natural category -> scored category."""
    if names is None:
        return NATURAL_ORDER
    order = [0] * 10
    for strength, name in enumerate(names):
        order[SPEC_CATEGORY_NAMES.index(name)] = strength
    order[FIVE_KIND] = FIVE_KIND         # five of a kind (wilds only) always on top
    return tuple(order)


# --------------------------------------------------------------------------- scoring

@dataclass(frozen=True)
class RankRules:
    """How a k-card hand is scored from rank positions (0 = lowest rank in the deck)."""
    k: int = 5
    n_ranks: int = 13
    straights: bool = True
    flushes: bool = True
    wheel: bool = True                 # top rank also plays low (A-2-3-4-5, short deck A-6-7-8-9)
    order: tuple[int, ...] = NATURAL_ORDER


def _straight_top(distinct_desc: list[int], rr: RankRules) -> Optional[int]:
    """Top position if the k distinct positions form a straight, else None."""
    k = rr.k
    if not rr.straights or k < 3 or len(distinct_desc) != k:
        return None
    if distinct_desc[0] - distinct_desc[-1] == k - 1:
        return distinct_desc[0]
    if rr.wheel and distinct_desc == [rr.n_ranks - 1] + list(range(k - 2, -1, -1)):
        return k - 2
    return None


def score_ranks(ranks: Sequence[int], flush: bool, rr: RankRules = RankRules()) -> int:
    """Value of a k-card hand given its rank positions and whether all suits match."""
    k = len(ranks)
    counts = Counter(ranks)
    groups = sorted(counts.items(), key=lambda rc: (rc[1], rc[0]), reverse=True)
    ordered = [r for r, c in groups for _ in range(c)]   # e.g. full house: trips rank first
    shape = [c for _, c in groups]
    flush = flush and rr.flushes and k >= 3
    top = _straight_top(sorted(counts, reverse=True), rr)

    if shape[0] >= 5:
        cat = FIVE_KIND
    elif top is not None and flush:
        cat, ordered = STRAIGHT_FLUSH, [top]
    elif shape[0] == 4:
        cat = QUADS
    elif shape[:2] == [3, 2]:
        cat = FULL_HOUSE
    elif flush:
        cat, ordered = FLUSH, sorted(ranks, reverse=True)
    elif top is not None:
        cat, ordered = STRAIGHT, [top]
    elif shape[0] == 3:
        cat = TRIPS
    elif shape[:2] == [2, 2]:
        cat = TWO_PAIR
    elif shape[0] == 2:
        cat = PAIR
    else:
        cat = HIGH_CARD
    packed = 0
    for i, r in enumerate(ordered[:MAX_HAND_SIZE]):
        packed |= r << (4 * (MAX_HAND_SIZE - 1 - i))
    return (rr.order[cat] << CATEGORY_SHIFT) | packed


# --------------------------------------------------------------------------- tables

# Sorting networks (compare-exchange pairs) for k <= 5 cards: on small int8 arrays these
# are several times faster than np.sort along a short last axis.
_NETWORKS = {
    1: [], 2: [(0, 1)], 3: [(0, 1), (1, 2), (0, 1)],
    4: [(0, 1), (2, 3), (0, 2), (1, 3), (1, 2)],
    5: [(0, 1), (3, 4), (2, 4), (2, 3), (0, 3), (0, 2), (1, 4), (1, 3), (1, 2)],
}


def sorted_columns(a: np.ndarray, n: int) -> list[np.ndarray]:
    """The first n entries along the last axis of `a`, sorted ascending, as n arrays."""
    cols = [a[..., i] for i in range(a.shape[-1])]
    for i, j in _NETWORKS[len(cols)]:
        lo, hi = np.minimum(cols[i], cols[j]), np.maximum(cols[i], cols[j])
        cols[i], cols[j] = lo, hi
    return cols[:n]


def _multiset_index(sorted_ranks: Sequence[int]) -> int:
    """Combinatorial index of a sorted rank multiset (r0 <= r1 <= ...)."""
    return sum(comb(r + i, i + 1) for i, r in enumerate(sorted_ranks))


class _Tables:
    """Score tables for one RankRules, indexed by sorted-multiset index.
    Wild tables (w > 0) are built lazily on first use."""

    def __init__(self, rr: RankRules) -> None:
        if not 1 <= rr.k <= MAX_HAND_SIZE:
            raise ValueError(f"hand_size must be 1..{MAX_HAND_SIZE}, got {rr.k}")
        if rr.n_ranks > 15:
            raise ValueError("at most 15 ranks")
        self.rr = rr
        self.k = rr.k
        n_max = rr.n_ranks + rr.k
        self.comb_np = np.array([[comb(n, j) for j in range(rr.k + 1)] for n in range(n_max)],
                                dtype=np.int64)
        self.comb_py = self.comb_np.tolist()
        self._wild: dict[int, tuple[np.ndarray, np.ndarray, list, list]] = {}
        self._base_tables()
        self.multi_np, self.flush_np, self.multi_py, self.flush_py = self._wild[0]

    def wild_tables(self, w: int):
        """(non-flush, flush) best scores for hands with w wild cards, indexed by the
        multiset of the k - w natural cards.

        Built recursively: one wild card is best used as whichever rank r maximises the
        (w - 1)-wild score of the hand with r added, so
            best_w(ms) = max over r of best_{w-1}(ms + r).
        That is a few thousand table lookups instead of re-scoring every filling."""
        if w not in self._wild:
            rr, n = self.rr, self.rr.k - w
            prev_multi, prev_flush, pm_py, pf_py = self.wild_tables(w - 1)
            size = comb(rr.n_ranks + n - 1, n) if n > 0 else 1
            multi = np.full(size, -1, dtype=np.int64)
            flush = np.full(size, -1, dtype=np.int64)
            for ms in itertools.combinations_with_replacement(range(rr.n_ranks), n):
                i = _multiset_index(ms)
                bm = bf = -1
                for r in range(rr.n_ranks):
                    j = _multiset_index(sorted(ms + (r,)))
                    bm = max(bm, pm_py[j])
                    bf = max(bf, pf_py[j])
                multi[i], flush[i] = bm, bf
            self._wild[w] = (multi, flush, multi.tolist(), flush.tolist())
        return self._wild[w]

    def _base_tables(self):
        """Natural (w = 0) tables: score every rank multiset, flush and non-flush."""
        rr = self.rr
        size = comb(rr.n_ranks + rr.k - 1, rr.k)
        multi = np.full(size, -1, dtype=np.int64)
        flush = np.full(size, -1, dtype=np.int64)
        for ms in itertools.combinations_with_replacement(range(rr.n_ranks), rr.k):
            i = _multiset_index(ms)
            multi[i] = score_ranks(ms, False, rr)
            flush[i] = score_ranks(ms, True, rr)
        self._wild[0] = (multi, flush, multi.tolist(), flush.tolist())

    def index_py(self, sorted_ranks: Sequence[int]) -> int:
        cp = self.comb_py
        return sum(cp[r + i][i + 1] for i, r in enumerate(sorted_ranks))

    def eval_py(self, pos: Sequence[int], suits: Sequence[int]) -> int:
        """Score one k-card hand without wilds (pure Python)."""
        idx = self.index_py(sorted(pos))
        if self.rr.flushes and all(s == suits[0] for s in suits):
            return self.flush_py[idx]
        return self.multi_py[idx]

    def eval_np(self, pos: np.ndarray, suits: np.ndarray, presorted: bool = False) -> np.ndarray:
        """Score hands of shape (..., k) without wilds."""
        cols = [pos[..., i] for i in range(self.k)] if presorted else sorted_columns(pos, self.k)
        idx = self.comb_np[cols[0], 1]
        for i in range(1, self.k):
            idx = idx + self.comb_np[cols[i] + i, i + 1]
        if not self.rr.flushes:
            return self.multi_np[idx]
        is_flush = (suits == suits[..., :1]).all(axis=-1)
        return np.where(is_flush, self.flush_np[idx], self.multi_np[idx])

    def eval_wild_np(self, pos: np.ndarray, suits: np.ndarray, wild: np.ndarray) -> np.ndarray:
        """Score hands of shape (..., k) where `wild` marks wild cards."""
        k = self.k
        w = wild.sum(axis=-1)
        ps = np.stack(sorted_columns(np.where(wild, 99, pos).astype(np.int8), k), axis=-1)
        s_hi = np.where(wild, -1, suits).max(axis=-1)
        s_lo = np.where(wild, 99, suits).min(axis=-1)
        flushable = (w == k) | (s_hi == s_lo)
        out = np.empty(w.shape, dtype=np.int64)
        for wv in np.unique(w):
            sel = w == wv
            n = k - int(wv)
            multi, flush, _, _ = self.wild_tables(int(wv))
            if n == 0:
                idx = np.zeros(int(sel.sum()), dtype=np.int64)
            else:
                sub = ps[sel]
                idx = self.comb_np[sub[:, 0], 1]
                for i in range(1, n):
                    idx = idx + self.comb_np[sub[:, i] + i, i + 1]
            vm = multi[idx]
            if self.rr.flushes:
                vm = np.where(flushable[sel], np.maximum(vm, flush[idx]), vm)
            out[sel] = vm
        return out

    def eval_wild_py(self, pos: Sequence[int], suits: Sequence[int], wild: Sequence[bool]) -> int:
        nat = sorted(p for p, wd in zip(pos, wild) if not wd)
        w = self.k - len(nat)
        multi, flush, multi_py, flush_py = self.wild_tables(w)
        idx = self.index_py(nat) if nat else 0
        v = multi_py[idx]
        nat_suits = {s for s, wd in zip(suits, wild) if not wd}
        if self.rr.flushes and len(nat_suits) <= 1:
            v = max(v, flush_py[idx])
        return v


@lru_cache(maxsize=None)
def tables_for(rr: RankRules) -> _Tables:
    return _Tables(rr)


def tables(k: int) -> _Tables:
    """Standard tables for hand size k (kept for benchmarks and old callers)."""
    return tables_for(RankRules(k=k))


# --------------------------------------------------------------------------- evaluator

def _standard_arrays():
    ids = np.arange(64)
    pos = np.where(ids < 52, ids // 4, -1).astype(np.int16)
    suit = np.where(ids < 52, ids % 4, -1).astype(np.int16)
    return pos, suit


_STD_POS, _STD_SUIT = _standard_arrays()


class HandEvaluator:
    """Best `hand_size`-card hand from hole + board under configurable rules.

    hole_exact=u        exactly u hole cards (Omaha: u = 2)
    hole_min / hole_max at least / at most that many hole cards
    deck                a bot.game.deck.Deck (default: standard 52)
    mode                "high" | "low_27" | "low_a5"
    order               category order (tuple from order_from_names) for "high"
    wild_ids            card ids that are wild
    qualifier           low_a5 only: highest allowed rank symbol, e.g. "8"
    """

    def __init__(self, hand_size: int = 5, hole_exact: Optional[int] = None,
                 hole_min: Optional[int] = None, hole_max: Optional[int] = None,
                 deck=None, mode: str = "high", order: tuple[int, ...] = NATURAL_ORDER,
                 wild_ids: Sequence[int] = (), qualifier: Optional[str] = None,
                 select_size: Optional[int] = None) -> None:
        if mode not in ("high", "low_27", "low_a5"):
            raise ValueError(f"unknown mode {mode!r}")
        # select_size k > 5: the hole/board rules pick k cards, which score as their best 5.
        self.select_size = select_size if select_size is not None else hand_size
        if self.select_size < hand_size:
            raise ValueError("select_size must be >= hand_size")
        self.hand_size = hand_size
        self.hole_exact, self.hole_min, self.hole_max = hole_exact, hole_min, hole_max
        self.hole_cards_used = hole_exact            # old name
        self.mode = mode
        self.low = mode != "high"
        if deck is None:
            pos, suit, n_ranks = _STD_POS, _STD_SUIT, 13
            size = 64
        else:
            pos = deck.pos_ace_low if mode == "low_a5" else deck.pos_high
            suit, n_ranks, size = deck.suit, deck.n_ranks, deck.size_ids
        if mode == "low_a5" and deck is None:
            pos = np.where(_STD_POS < 0, -1, (_STD_POS + 1) % 13).astype(np.int16)
        # Fast path: standard 52-card ids with standard rank order -> pos = id >> 2.
        self._bitpath = (mode != "low_a5" and (deck is None or (
            deck.n_ranks == 13 and deck.jokers == 0 and deck.copies == 1)))
        self.pos_np = np.asarray(pos, dtype=np.int8)
        self.suit_np = np.asarray(suit, dtype=np.int8)
        self.pos_py = self.pos_np.tolist()
        self.suit_py = self.suit_np.tolist()
        wild = np.zeros(max(size, 1), dtype=bool)
        for c in wild_ids:
            if c < len(wild):
                wild[c] = True
        self.wild_np = wild
        self.wild_py = wild.tolist()
        self.has_wild = bool(wild.any())
        rr = RankRules(hand_size, n_ranks, straights=mode != "low_a5",
                       flushes=mode != "low_a5", wheel=mode == "high",
                       order=order if mode == "high" else NATURAL_ORDER)
        self._t = tables_for(rr)
        self.q_pos = None
        if qualifier is not None:
            if mode != "low_a5":
                raise ValueError("qualifier needs mode low_a5")
            seq = list(deck.ranks if deck is not None else "23456789TJQKA")
            if "A" in seq:
                seq = ["A"] + [r for r in seq if r != "A"]
            self.q_pos = seq.index(qualifier)

    # ---- combinations
    @lru_cache(maxsize=64)
    def combos(self, n_hole: int, n_board: int) -> tuple[tuple[int, ...], ...]:
        """Index tuples into (hole + board) for every k-card combination to score."""
        picks = self._selections(n_hole, n_board)
        if self.select_size == self.hand_size:
            return picks
        seen = {sub for pick in picks for sub in itertools.combinations(pick, self.hand_size)}
        return tuple(sorted(seen))

    def _selections(self, n_hole: int, n_board: int) -> tuple[tuple[int, ...], ...]:
        """Every allowed choice of select_size cards under the hole-card rules."""
        k = self.select_size
        if self.hole_exact is not None:
            lo = hi = self.hole_exact
        else:
            lo = max(self.hole_min or 0, k - n_board)
            hi = min(self.hole_max if self.hole_max is not None else k, k, n_hole)
        if lo > hi or n_hole < lo or n_board < k - hi:
            raise ValueError(f"cannot make a {k}-card hand from {n_hole} hole + {n_board} board "
                             f"cards under these hole-card rules")
        board_idx = range(n_hole, n_hole + n_board)
        out = []
        for u in range(lo, hi + 1):
            out += [h + b for h in itertools.combinations(range(n_hole), u)
                    for b in itertools.combinations(board_idx, k - u)]
        return tuple(out)

    @lru_cache(maxsize=64)
    def _combos_np(self, n_hole: int, n_board: int) -> np.ndarray:
        return np.array(self.combos(n_hole, n_board), dtype=np.intp)

    @property
    def unrestricted(self) -> bool:
        return self.hole_exact is None and self.hole_min is None and self.hole_max is None

    # ---- low-mode transform
    def _finish_py(self, v: int) -> int:
        if not self.low:
            return v
        if self.q_pos is not None and not (v >> CATEGORY_SHIFT == HIGH_CARD
                                           and (v >> 16) & 15 <= self.q_pos):
            return NOT_QUALIFIED
        return LOW_BASE - v

    def _finish_np(self, v: np.ndarray) -> np.ndarray:
        if not self.low:
            return v
        out = LOW_BASE - v
        if self.q_pos is not None:
            ok = ((v >> CATEGORY_SHIFT) == HIGH_CARD) & (((v >> 16) & 15) <= self.q_pos)
            out = np.where(ok, out, NOT_QUALIFIED)
        return out

    # ---- evaluation
    def evaluate(self, hole: Sequence[int], board: Sequence[int]) -> int:
        """Value of the best hand for one player (pure Python, no NumPy overhead)."""
        cards = list(hole) + list(board)
        pos = [self.pos_py[c] for c in cards]
        suit = [self.suit_py[c] for c in cards]
        t = self._t
        best = NOT_QUALIFIED - 1
        if self.has_wild:
            wild = [self.wild_py[c] for c in cards]
            for combo in self.combos(len(hole), len(board)):
                v = self._finish_py(t.eval_wild_py([pos[i] for i in combo], [suit[i] for i in combo],
                                                   [wild[i] for i in combo]))
                best = v if v > best else best
        else:
            for combo in self.combos(len(hole), len(board)):
                v = self._finish_py(t.eval_py([pos[i] for i in combo], [suit[i] for i in combo]))
                best = v if v > best else best
        return best

    def evaluate_batch(self, hole: np.ndarray, board: np.ndarray) -> np.ndarray:
        """Best-hand values for many players at once.

        hole: (B, h) or (h,);  board: (B, b) or (b,). 1-D inputs are broadcast over the
        batch. Returns an int64 array of shape (B,).
        """
        hole = np.atleast_2d(np.asarray(hole, dtype=np.intp))
        board = np.asarray(board, dtype=np.intp)
        board = board.reshape(1, -1) if board.ndim == 1 else board
        n = max(hole.shape[0], board.shape[0])
        hole = np.broadcast_to(hole, (n, hole.shape[1]))
        board = np.broadcast_to(board, (n, board.shape[1]))
        cards = np.concatenate([hole, board], axis=1)
        combos = self._combos_np(hole.shape[1], board.shape[1])
        if self._bitpath and not self.has_wild:
            presorted = self.unrestricted
            if presorted:
                cards = np.sort(cards, axis=1)      # id order = rank order here
            sub = cards.astype(np.int8)[:, combos]
            return self._finish_np(self._t.eval_np(sub >> 2, sub & 3, presorted)).max(axis=1)
        pos = self.pos_np[cards]
        suit = self.suit_np[cards]
        if self.has_wild:
            wild = self.wild_np[cards]
            v = self._t.eval_wild_np(pos[:, combos], suit[:, combos], wild[:, combos])
        else:
            # With no hole/board restriction, sort each hand once: combos pick ascending
            # positions, so every k-card subset is then already sorted by rank.
            presorted = self.unrestricted
            if presorted:
                order = np.argsort(pos, axis=1, kind="stable")
                pos = np.take_along_axis(pos, order, axis=1)
                suit = np.take_along_axis(suit, order, axis=1)
            v = self._t.eval_np(pos[:, combos], suit[:, combos], presorted)
        return self._finish_np(v).max(axis=1)

    def evaluate_5(self, cards: Sequence[int]) -> int:
        """Score exactly `hand_size` cards (no combination search)."""
        c = list(cards)
        return self._finish_py(self._t.eval_py([self.pos_py[x] for x in c],
                                               [self.suit_py[x] for x in c]))

    def warm_up(self) -> None:
        """Build every lazy table now (wild tables can take ~1 s in pure Python)."""
        if self.has_wild:
            for w in range(1, self.hand_size + 1):
                self._t.wild_tables(w)


class GenericEvaluator(HandEvaluator):
    """Standard high-hand evaluator (old signature): best `hand_size` cards, optionally
    exactly `hole_cards_used` hole cards."""

    def __init__(self, hand_size: int = 5, hole_cards_used: Optional[int] = None) -> None:
        super().__init__(hand_size, hole_exact=hole_cards_used)
