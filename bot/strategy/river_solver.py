"""Anytime river solver: vector CFR+ for ONE river decision (RA spike, Tier 4 sub-plan R).

Input: our range and their range as weights over 2-card combos (card removal against the
board and each other is exact), the pot, the stacks and the current street bets. The tree
starts at the current node with the real amounts; the menu is fold / call / check plus bets
and raises of a few pot fractions and all-in, at most `max_aggr` bets+raises on the street.

Method
------
Simultaneous-update CFR+ (regrets floored at 0, linear averaging). Every pass works on
whole vectors of hands: the tree is built once (BFS order, children of a node contiguous),
so the forward reach pass, the backward value pass and the regret update are a handful of
NumPy calls per tree depth, not per node.

Terminals, with card removal in O(n) per terminal:
  showdown   value of hand i = sum_j z_j sign(rank_i - rank_j) over opp combos j that share
             no card with i. Inclusion-exclusion over i's two cards: all combos, minus
             combos holding card 1, minus combos holding card 2 (the combo equal to i has
             sign 0, so nothing to add back). Prefix sums over the combos sorted by rank
             (and per card, sorted by rank) turn each sum into a few gathers; all the index
             arrays are built once per spot.
  fold       sum_j z_j over compatible j = total - card1 sums - card2 sums + same-combo.

Payoffs are in pot units (chips / pot at the root); the money already in the pot counts
(utility = chips won - chips put in over the whole hand), so the game is zero-sum.

Anytime: `RiverSolver.run(deadline)` stops at the deadline (a `time.perf_counter()` value)
and `solve_river` returns the average strategy for our actual hand at the root.
NumPy only; no files, no processes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

INF = float("inf")
AVG_POWER = 2                       # averaging weight = pass number ** AVG_POWER
_BIG = 1 << 26                      # > any evaluator value; keys = card * _BIG + rank
FOLD, CALL, CHECK, RAISE = "F", "C", "K", "R"

# ------------------------------------------------------------------ the spot and the tree


@dataclass(frozen=True)
class RiverSpot:
    """The river decision, in the engine's own terms (all amounts in chips).

    pot         chips in the pot now (including the bets on this street)
    hero_bet    our chips in on this street; opp_bet theirs (to-call = opp_bet - hero_bet)
    hero_stack  chips we still hold behind; opp_stack theirs
    last_raise  size of the last bet/raise on this street (0 if none): sets the min raise
    aggr_so_far bets/raises already made on this street
    checked     the opponent has already checked (so our check ends the street)
    """
    pot: float
    hero_bet: float = 0.0
    opp_bet: float = 0.0
    hero_stack: float = 200.0
    opp_stack: float = 200.0
    last_raise: float = 0.0
    aggr_so_far: int = 0
    checked: bool = False


@dataclass(frozen=True)
class TreeCfg:
    bet_sizes: tuple = (0.5, 1.0, INF)      # fractions of the pot; INF = all-in
    raise_sizes: tuple = (0.5, 1.0, INF)    # fractions of the pot after calling
    max_aggr: int = 3                       # bets + raises on the street (a bet and 2 raises)
    min_bet: float = 2.0                    # the engine's minimum bet / raise increment


class Tree:
    """Betting tree in BFS order: children of a node are contiguous, depth blocks are
    contiguous, and hero (player 0) acts at even depths, the opponent at odd depths."""

    def __init__(self, spot: RiverSpot, cfg: TreeCfg = TreeCfg()) -> None:
        self.spot, self.cfg = spot, cfg
        L = [float(spot.hero_bet), float(spot.opp_bet)]
        stack = [float(spot.hero_stack), float(spot.opp_stack)]
        pot = float(spot.pot)
        cap = min(L[0] + stack[0], L[1] + stack[1])           # the effective all-in level
        for p in (0, 1):                                      # a bet above the cap is refunded
            if L[p] > cap:
                pot -= L[p] - cap
                L[p] = cap
        self.cap = cap
        self.unit = max(pot, 1e-9)                            # payoffs are chips / unit
        self.sunk = max((pot - L[0] - L[1]) / 2.0, 0.0)       # what each had in before the street
        last = float(spot.last_raise) or max(L[1] - L[0], L[0] - L[1], 0.0)
        self.kind: list[int] = []          # 0 decision, 1 fold terminal, 2 showdown terminal
        self.depth: list[int] = []
        self.parent: list[int] = []
        self.slot: list[int] = []
        self.children: list[list[int]] = []
        self.label: list[tuple] = []       # (kind, level) of the action that led here
        self.term: list[tuple] = []        # terminals: (coef_hero, coef_opp) in pot units
        self.legal_labels: list[list[tuple]] = []
        queue = [(L[0], L[1], pot, last, int(spot.aggr_so_far), bool(spot.checked), -1, -1, None)]
        i = 0
        while i < len(queue):
            l0, l1, pt, lst, na, chk, par, slot, lab = queue[i]
            nid = i
            i += 1
            d = 0 if par < 0 else self.depth[par] + 1
            self.depth.append(d)
            self.parent.append(par)
            self.slot.append(slot)
            self.children.append([])
            self.label.append(lab if lab is not None else ("ROOT", 0.0))
            self.kind.append(0)
            self.term.append((0.0, 0.0))
            self.legal_labels.append([])
            if par >= 0:
                self.children[par].append(nid)
            if lab is not None and lab[0] == "T":                 # a terminal: resolve, no actions
                _, ty, a, lev = lab
                self.kind[nid] = ty
                c = (self.sunk + lev) / self.unit
                self.term[nid] = ((-c, c) if a == 0 else (c, -c)) if ty == 1 else (c, c)
                self.label[nid] = self.legal_labels[par][slot]
                continue
            # the node at depth d is decided by hero when d is even
            a = d % 2
            la, lo = (l0, l1) if a == 0 else (l1, l0)
            facing = lo > la
            acts: list[tuple] = []                          # (label, child tuple or terminal)
            if facing:
                acts.append(((FOLD, la), ("fold", a, la)))
                acts.append(((CALL, lo), ("show", lo)))
            else:
                acts.append(((CHECK, la), ("show", la) if chk else ("node", la, lo, pt, lst, na, True)))
            if na < cfg.max_aggr and cap > max(la, lo) + 1e-9:
                call_level = lo if facing else la
                pot_ac = pt + (lo - la)
                min_inc = max(lst, cfg.min_bet)
                sizes = cfg.raise_sizes if facing else cfg.bet_sizes
                levels = []
                for f in sizes:
                    t = cap if f == INF else call_level + max(f * pot_ac, min_inc)
                    if t >= cap - 1e-9 or cap - t < min_inc * 0.5:
                        t = cap
                    if t > call_level + 1e-9 and all(abs(t - u) > 1e-9 for u in levels):
                        levels.append(t)
                for t in sorted(levels):
                    acts.append(((RAISE, t), ("node", t, lo, pt + (t - la), t - call_level, na + 1, False)))
            self.legal_labels[nid] = [x[0] for x in acts]
            for k, (lab_k, nxt) in enumerate(acts):
                if nxt[0] == "node":
                    _, ta, tlo, tpt, tlst, tna, tchk = nxt
                    # next node is decided by the other player: store levels as (l0, l1)
                    n_l0, n_l1 = (ta, tlo) if a == 0 else (tlo, ta)
                    queue.append((n_l0, n_l1, tpt, tlst, tna, tchk, nid, k, lab_k))
                elif nxt[0] == "fold":
                    queue.append((0.0, 0.0, 0.0, 0.0, 0, False, nid, k, ("T", 1, a, nxt[2])))
                else:
                    queue.append((0.0, 0.0, 0.0, 0.0, 0, False, nid, k, ("T", 2, a, nxt[1])))
        self.n = len(self.kind)
        self.max_depth = max(self.depth)
        self.dec_ids = [i for i in range(self.n) if self.kind[i] == 0]
        # nodes at depth d form a contiguous block [start, end)
        self.block: list[tuple[int, int]] = []
        for d in range(self.max_depth + 1):
            ids = [i for i in range(self.n) if self.depth[i] == d]
            self.block.append((ids[0], ids[-1] + 1))

    @property
    def root_labels(self) -> list[tuple]:
        return self.legal_labels[0]


def _tree_stats(t: Tree) -> dict:
    return {"nodes": t.n, "decisions": len(t.dec_ids),
            "showdowns": sum(1 for k in t.kind if k == 2), "folds": sum(1 for k in t.kind if k == 1),
            "depth": t.max_depth}


# ------------------------------------------------------------------ terminal kernels
#
# A kernel answers four questions for a batch of terminals (rows of z = the OTHER player's
# reach vectors): the value of every hand of ours at a showdown / at a fold, and the same
# for the opponent. Showdown value of hand i = sum_j z_j sign(rank_i - rank_j) over the
# compatible j; fold value = sum_j z_j over the compatible j.


class _Dir:
    """Index arrays for 'values of a-hands from a reach vector over b-hands', O(n) per row:
    prefix sums over the b-combos sorted by rank, and per card sorted by rank; the combos
    sharing a card with hand i are removed by inclusion-exclusion over its two cards (the
    combo equal to i has sign 0, so nothing is added back for the showdown)."""

    def __init__(self, rank_a, cards_a, rank_b, cards_b, dtype) -> None:
        na, nb = len(rank_a), len(rank_b)
        self.na, self.nb = na, nb
        order_b = np.argsort(rank_b, kind="stable")
        rs = rank_b[order_b]
        lo = np.searchsorted(rs, rank_a, "left")
        hi = np.searchsorted(rs, rank_a, "right")
        ent_card = np.concatenate([cards_b[:, 0], cards_b[:, 1]]).astype(np.int64)
        ent_idx = np.concatenate([np.arange(nb), np.arange(nb)])
        keys = ent_card * _BIG + rank_b[ent_idx]
        oe = np.argsort(keys, kind="stable")
        keys_s = keys[oe]
        perm_e = ent_idx[oe]
        b2 = nb + 1
        plus = [lo, hi]
        minus = [np.full(na, nb)]
        for k in (0, 1):
            c = cards_a[:, k].astype(np.int64)
            q = c * _BIG + rank_a
            lo_c = np.searchsorted(keys_s, q, "left")
            hi_c = np.searchsorted(keys_s, q, "right")
            st = np.searchsorted(keys_s, c * _BIG, "left")
            en = np.searchsorted(keys_s, (c + 1) * _BIG, "left")
            minus += [b2 + lo_c, b2 + hi_c]
            plus += [b2 + st, b2 + en]
        self.plus = np.stack(plus).astype(np.intp)        # (6, na)
        self.minus = np.stack(minus).astype(np.intp)      # (5, na)
        self.order_b = order_b.astype(np.intp)
        self.perm_e = perm_e.astype(np.intp)
        self.width = 1 + nb + 1 + 2 * nb
        inc = np.zeros((nb, 52))
        inc[np.arange(nb), cards_b[:, 0]] = 1.0
        inc[np.arange(nb), cards_b[:, 1]] = 1.0
        self.inc = inc.astype(dtype)
        self.c1 = cards_a[:, 0].astype(np.intp)
        self.c2 = cards_a[:, 1].astype(np.intp)
        lookup = {}
        for j in range(nb):
            a_, b_ = int(cards_b[j, 0]), int(cards_b[j, 1])
            lookup[(a_, b_)] = lookup[(b_, a_)] = j
        same = np.array([lookup.get((int(cards_a[i, 0]), int(cards_a[i, 1])), -1) for i in range(na)])
        self.same = np.maximum(same, 0).astype(np.intp)
        self.same_mask = (same >= 0).astype(dtype)
        self.buf: Optional[np.ndarray] = None
        self.dt = dtype

    def show(self, z: np.ndarray) -> np.ndarray:
        """z (T, nb) -> (T, na)."""
        nb = self.nb
        if self.buf is None or self.buf.shape[0] != z.shape[0]:
            self.buf = np.zeros((z.shape[0], self.width), dtype=self.dt)
        buf = self.buf
        buf[:, 0] = 0.0
        buf[:, 1:nb + 1] = z[:, self.order_b]
        buf[:, nb + 1] = 0.0
        buf[:, nb + 2:] = z[:, self.perm_e]
        np.cumsum(buf, axis=1, out=buf)
        return buf[:, self.plus].sum(axis=1) - buf[:, self.minus].sum(axis=1)

    def fold(self, z: np.ndarray) -> np.ndarray:
        cs = z @ self.inc
        return (z.sum(axis=1, keepdims=True) - cs[:, self.c1] - cs[:, self.c2]
                + z[:, self.same] * self.same_mask)


class SortedKernel:
    """Exact card removal, O(n) per terminal (best for large ranges)."""

    def __init__(self, hero_cards, hero_rank, opp_cards, opp_rank, dtype=np.float32) -> None:
        self.d0 = _Dir(hero_rank, hero_cards, opp_rank, opp_cards, dtype)
        self.d1 = _Dir(opp_rank, opp_cards, hero_rank, hero_cards, dtype)
        self.n0, self.n1 = len(hero_rank), len(opp_rank)

    def show0(self, z1): return self.d0.show(z1)
    def show1(self, z0): return self.d1.show(z0)
    def fold0(self, z1): return self.d0.fold(z1)
    def fold1(self, z0): return self.d1.fold(z0)


class DenseKernel:
    """Payoff matrix M[i, j] = sign(rank_i - rank_j) (times a compatibility mask when cards
    are given: exact card removal) and matrix products. Fastest for n up to a few hundred."""

    def __init__(self, M: np.ndarray, compat: Optional[np.ndarray] = None, dtype=np.float32) -> None:
        self.M = np.ascontiguousarray(M, dtype=dtype)
        self.MT = np.ascontiguousarray(self.M.T)
        self.compat = None if compat is None else np.ascontiguousarray(compat, dtype=dtype)
        self.compatT = None if compat is None else np.ascontiguousarray(self.compat.T)
        self.n0, self.n1 = self.M.shape

    @classmethod
    def exact(cls, hero_cards, hero_rank, opp_cards, opp_rank, dtype=np.float32) -> "DenseKernel":
        a = np.asarray(hero_cards)
        b = np.asarray(opp_cards)
        share = ((a[:, 0, None] == b[None, :, 0]) | (a[:, 0, None] == b[None, :, 1])
                 | (a[:, 1, None] == b[None, :, 0]) | (a[:, 1, None] == b[None, :, 1]))
        compat = (~share).astype(np.float64)
        M = np.sign(hero_rank[:, None] - opp_rank[None, :]) * compat
        return cls(M, compat, dtype)

    def show0(self, z1): return z1 @ self.MT
    def show1(self, z0): return -(z0 @ self.M)

    def fold0(self, z1):
        return z1.sum(axis=1, keepdims=True) if self.compat is None else z1 @ self.compatT

    def fold1(self, z0):
        return z0.sum(axis=1, keepdims=True) if self.compat is None else z0 @ self.compat


def bucket_ranges(rank: np.ndarray, w: np.ndarray, n_buckets: int, always: Optional[int] = None):
    """Split a range into at most `n_buckets` contiguous strength buckets of about equal weight.
    Returns (bucket id per combo, bucket weights). `always` (a combo index) is guaranteed
    its own bucket id (it is just assigned like any other combo)."""
    order = np.argsort(rank, kind="stable")
    cum = np.cumsum(w[order]) / w.sum()
    b = np.minimum((cum - 1e-12) * n_buckets, n_buckets - 1).astype(np.int64)
    b = np.maximum(b, 0)
    ids = np.empty(len(rank), dtype=np.int64)
    ids[order] = b
    # drop empty buckets
    used = np.unique(ids)
    remap = np.full(n_buckets, -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    ids = remap[ids]
    bw = np.bincount(ids, weights=w, minlength=len(used))
    return ids, bw


def bucket_kernel(hero_rank, hero_w, hero_b, opp_rank, opp_w, opp_b, dtype=np.float32,
                  hero_cards=None, opp_cards=None) -> DenseKernel:
    """Bucket-vs-bucket expected showdown sign. Built from prefix sums over the opponent's
    sorted combos: O((n0 + n1) log n + n0 * B1). With the combos' cards given, card removal is
    kept at bucket level: the mass of pairs sharing a card (from per-bucket card histograms:
    one B x 52 x B product) scales the sign matrix and gives the fold (compatibility) matrix."""
    nb0 = int(hero_b.max()) + 1
    nb1 = int(opp_b.max()) + 1
    order = np.argsort(opp_rank, kind="stable")
    rs = opp_rank[order]
    C = np.concatenate([[0.0], np.cumsum(opp_w[order])])
    # buckets are contiguous in the rank order (bucket_ranges cut them on it)
    start = np.searchsorted(opp_b[order], np.arange(nb1), "left")
    end = np.searchsorted(opp_b[order], np.arange(nb1), "right")
    oh = np.argsort(hero_rank, kind="stable")
    hs = hero_rank[oh]
    hstart = np.searchsorted(hero_b[oh], np.arange(nb0), "left")
    hend = np.searchsorted(hero_b[oh], np.arange(nb0), "right")
    hw = np.bincount(hero_b, weights=hero_w, minlength=nb0)
    ow = np.bincount(opp_b, weights=opp_w, minlength=nb1)
    pair = hw[:, None] * ow[None, :]
    # a pair of buckets whose rank ranges do not overlap has a constant sign; only the overlapping
    # pairs (a band along the diagonal) need the per-member sums
    sg = (hs[hstart][:, None] > rs[end - 1][None, :]).astype(np.float64) \
        - (hs[hend - 1][:, None] < rs[start][None, :])
    Mw = sg * pair
    ia, ib = np.nonzero(sg == 0)
    cnt = hend[ia] - hstart[ia]
    pidx = np.repeat(np.arange(len(ia)), cnt)
    pos = np.arange(len(pidx)) - np.repeat(np.cumsum(cnt) - cnt, cnt) + hstart[ia][pidx]
    b = ib[pidx]
    r_i = hs[pos]
    lt = C[np.clip(np.searchsorted(rs, r_i, "left"), start[b], end[b])] - C[start[b]]
    le = C[np.clip(np.searchsorted(rs, r_i, "right"), start[b], end[b])] - C[start[b]]
    Mw[ia, ib] = np.bincount(pidx, hero_w[oh][pos] * (lt + le - ow[b]), len(ia))
    M = Mw / pair
    if hero_cards is None:
        return DenseKernel(M, None, dtype)
    hc = np.asarray(hero_cards, dtype=np.int64)
    oc = np.asarray(opp_cards, dtype=np.int64)
    U = (np.bincount(hero_b * 52 + hc[:, 0], hero_w, nb0 * 52)
         + np.bincount(hero_b * 52 + hc[:, 1], hero_w, nb0 * 52)).reshape(nb0, 52)
    T = (np.bincount(opp_b * 52 + oc[:, 0], opp_w, nb1 * 52)
         + np.bincount(opp_b * 52 + oc[:, 1], opp_w, nb1 * 52)).reshape(nb1, 52)
    share = U @ T.T                                       # pairs sharing a card; a shared pair counted twice
    ok = np.sort(oc, axis=1)
    hk = np.sort(hc, axis=1)
    okey = ok[:, 0] * 52 + ok[:, 1]
    oo = np.argsort(okey)
    pos = np.minimum(np.searchsorted(okey[oo], hk[:, 0] * 52 + hk[:, 1]), len(okey) - 1)
    j = oo[pos]
    same = okey[j] == hk[:, 0] * 52 + hk[:, 1]            # the same combo on both sides
    if same.any():
        i = np.nonzero(same)[0]
        share -= np.bincount(hero_b[i] * nb1 + opp_b[j[i]], hero_w[i] * opp_w[j[i]],
                             nb0 * nb1).reshape(nb0, nb1)
    compat = 1.0 - share / pair
    return DenseKernel(M * compat, compat, dtype)


# ------------------------------------------------------------------ the solver


class RiverSolver:
    """State of one solve. Build it (setup cost), then `run(deadline)`; read the result.

    All tensors are (node, player, hand): hero is player 0, the opponent player 1, both
    padded to N = max(n0, n1) hands (padded hands have zero weight and zero value)."""

    def __init__(self, spot: RiverSpot, w0, w1, kernel, cfg: TreeCfg = TreeCfg(),
                 dtype=np.float32, track_all: bool = False) -> None:
        self.dt = dtype
        self.tree = t = Tree(spot, cfg)
        self.kernel = kernel
        self.n0, self.n1 = len(w0), len(w1)
        N = self.N = max(self.n0, self.n1)
        w0 = np.asarray(w0, dtype=np.float64)
        w1 = np.asarray(w1, dtype=np.float64)
        self.w0 = (w0 / w0.sum()).astype(dtype)
        self.w1 = (w1 / w1.sum()).astype(dtype)
        V = self.V = t.n
        kinds = np.array(t.kind)
        self.fold_ids = np.nonzero(kinds == 1)[0]
        self.show_ids = np.nonzero(kinds == 2)[0]
        term = np.array(t.term, dtype=np.float64)
        self.fold_c0 = term[self.fold_ids, 0, None].astype(dtype)
        self.fold_c1 = term[self.fold_ids, 1, None].astype(dtype)
        self.show_c = term[self.show_ids, 0, None].astype(dtype)
        self.dec = np.array(t.dec_ids, dtype=np.intp)                # decision node ids (BFS order)
        D = len(self.dec)
        self.row_of = {int(n): r for r, n in enumerate(self.dec)}
        self.actor = np.array([t.depth[n] % 2 for n in self.dec], dtype=np.intp)
        K = self.K = max(len(t.children[n]) for n in self.dec)
        mask = np.zeros((D, K, 1), dtype=dtype)
        child_idx = np.full((D, K), V, dtype=np.intp)                # V = the all-zero dummy row
        for r, n in enumerate(self.dec):
            for k, c in enumerate(t.children[n]):
                mask[r, k, 0] = 1.0
                child_idx[r, k] = c
        self.mask, self.child_idx = mask, child_idx
        self.unif = mask / np.maximum(mask.sum(axis=1, keepdims=True), 1.0)
        # every non-root node: the row, slot and actor of the decision that led to it
        ids = np.arange(1, V)
        self.f_ids = ids
        self.f_row = np.array([self.row_of[t.parent[n]] for n in ids], dtype=np.intp)
        self.f_slot = np.array([t.slot[n] for n in ids], dtype=np.intp)
        self.f_actor = np.array([t.depth[t.parent[n]] % 2 for n in ids], dtype=np.intp)
        # per depth: the block of children, parents, reduceat starts
        self.levels = []
        for d in range(t.max_depth):
            dn = [n for n in t.dec_ids if t.depth[n] == d]
            if not dn:
                continue
            cs, ce = t.block[d + 1]
            starts = np.array([t.children[n][0] - cs for n in dn], dtype=np.intp)
            par = np.array([t.parent[c] for c in range(cs, ce)], dtype=np.intp)
            self.levels.append((np.array(dn, dtype=np.intp), cs, ce, par, starts))
        self.Q = np.zeros((V + 1, 2, N), dtype=dtype)
        self.Val = np.zeros((V + 1, 2, N), dtype=dtype)
        self.Fc = np.ones((V + 1, 2, N), dtype=dtype)
        self.Q[0, 0, :self.n0] = self.w0
        self.Q[0, 1, :self.n1] = self.w1
        self.R = np.zeros((D, K, N), dtype=dtype)
        self.track_all = track_all
        self.avg_power = AVG_POWER
        self.A = np.zeros((D, K, N), dtype=dtype) if track_all else np.zeros((1, K, N), dtype=dtype)
        self.iterations = 0

    # ---- one pass
    def step(self) -> None:
        Q, Val, Fc, R = self.Q, self.Val, self.Fc, self.R
        pos = R + 1e-30
        pos *= self.mask
        S = pos / pos.sum(axis=1, keepdims=True)                     # (D, K, N)
        Fc[self.f_ids, self.f_actor] = S[self.f_row, self.f_slot]    # factor of the acting player
        for dn, cs, ce, par, starts in self.levels:
            Q[cs:ce] = Q[par] * Fc[cs:ce]
        k, n0, n1 = self.kernel, self.n0, self.n1
        if len(self.fold_ids):
            qf = Q[self.fold_ids]
            Val[self.fold_ids, 0, :n0] = self.fold_c0 * k.fold0(qf[:, 1, :n1])
            Val[self.fold_ids, 1, :n1] = self.fold_c1 * k.fold1(qf[:, 0, :n0])
        if len(self.show_ids):
            qs = Q[self.show_ids]
            Val[self.show_ids, 0, :n0] = self.show_c * k.show0(qs[:, 1, :n1])
            Val[self.show_ids, 1, :n1] = self.show_c * k.show1(qs[:, 0, :n0])
        for dn, cs, ce, par, starts in reversed(self.levels):
            Val[dn] = np.add.reduceat(Val[cs:ce] * Fc[cs:ce], starts, axis=0)
        cv = Val[self.child_idx, self.actor[:, None]]               # (D, K, N)
        nv = Val[self.dec, self.actor]                              # (D, N)
        cv -= nv[:, None, :]
        cv *= self.mask
        R += cv
        np.maximum(R, 0.0, out=R)
        w = (self.iterations + 1) ** self.avg_power
        if self.track_all:
            self.A += (w * Q[self.dec, self.actor])[:, None, :] * S
        else:
            self.A[0] += (w * self.w0_pad)[None, :] * S[0]           # the root is a hero node
        self.iterations += 1

    @property
    def w0_pad(self) -> np.ndarray:
        if getattr(self, "_w0p", None) is None:
            self._w0p = np.zeros(self.N, dtype=self.dt)
            self._w0p[:self.n0] = self.w0
        return self._w0p

    def run(self, deadline: float, max_iters: int = 10**9, min_iters: int = 0) -> int:
        """Iterate until `deadline` (a perf_counter value) or `max_iters`. Returns the count."""
        n = 0
        while n < max_iters and (n < min_iters or time.perf_counter() < deadline):
            self.step()
            n += 1
        return n

    # ---- results
    def root_strategy(self, hero_index: int) -> np.ndarray:
        """Average strategy at the root for our hand (or bucket) `hero_index`."""
        k = len(self.tree.children[0])
        a = self.A[0, :k, hero_index].astype(np.float64)
        tot = a.sum()
        return a / tot if tot > 0 else np.full(k, 1.0 / k)

    def average(self, p: int = None) -> np.ndarray:
        """Average strategy (D, K, N) of the decision nodes (needs track_all=True)."""
        assert self.track_all, "build the solver with track_all=True"
        tot = self.A.sum(axis=1, keepdims=True)
        return np.where(tot > 0, self.A / np.maximum(tot, 1e-30), self.unif).astype(np.float64)

    def exploitability(self, avg: Optional[np.ndarray] = None, kernel=None, weights=None) -> float:
        """(BR_0 + BR_1) / 2 of a strategy profile (default: our average), in pot units
        (one pot = 1.0), by a vector best response over the same tree. 0 at equilibrium.
        `kernel` and `weights` = (w0, w1) evaluate it in another game (for example the exact
        full-size game, for a strategy that was solved in a bucketed one)."""
        t, V = self.tree, self.V
        avg = self.average() if avg is None else avg
        k = kernel or self.kernel
        w0, w1 = weights if weights is not None else (self.w0[:self.n0], self.w1[:self.n1])
        w0 = np.asarray(w0, dtype=np.float64) / np.sum(w0)
        w1 = np.asarray(w1, dtype=np.float64) / np.sum(w1)
        n0, n1, N = len(w0), len(w1), avg.shape[2]
        Q = np.zeros((V + 1, 2, N))
        Q[0, 0, :n0] = w0
        Q[0, 1, :n1] = w1
        F = np.ones((V + 1, 2, N))
        F[self.f_ids, self.f_actor] = avg[self.f_row, self.f_slot]
        for dn, cs, ce, par, starts in self.levels:
            Q[cs:ce] = Q[par] * F[cs:ce]
        z = float((k.fold0(Q[0:1, 1, :n1].astype(self.dt))[0] * w0).sum())
        total = 0.0
        for br in (0, 1):
            o = 1 - br
            Val = np.zeros((V + 1, N))
            nb, no = (n0, n1) if br == 0 else (n1, n0)
            fold, cf = (k.fold0, self.fold_c0) if br == 0 else (k.fold1, self.fold_c1)
            show = k.show0 if br == 0 else k.show1
            if len(self.fold_ids):
                Val[self.fold_ids, :nb] = cf * fold(Q[self.fold_ids, o, :no].astype(self.dt))
            if len(self.show_ids):
                Val[self.show_ids, :nb] = self.show_c * show(Q[self.show_ids, o, :no].astype(self.dt))
            for dn, cs, ce, par, starts in reversed(self.levels):
                if (t.depth[int(dn[0])] % 2) == br:
                    Val[dn] = np.maximum.reduceat(Val[cs:ce], starts, axis=0)
                else:
                    Val[dn] = np.add.reduceat(Val[cs:ce], starts, axis=0)
            total += float(Val[0, :nb] @ Q[0, br, :nb])
        return 0.5 * total / z


@dataclass
class SolveResult:
    labels: list                 # root actions: (kind, level) -- level = our street total for a raise
    probs: np.ndarray            # our average strategy at the root for our actual hand
    iterations: int
    setup_s: float
    run_s: float
    solver: Optional[RiverSolver] = None


def make_kernel(hero_cards, hero_rank, opp_cards, opp_rank, kernel: str = "auto", dtype=np.float32):
    """Exact card-removal kernel: "dense" (matrix products; best up to a few hundred combos),
    "sorted" (O(n) per terminal) or "auto" (dense when both ranges have <= 400 combos)."""
    hc = np.asarray(hero_cards, dtype=np.int64).reshape(-1, 2)
    oc = np.asarray(opp_cards, dtype=np.int64).reshape(-1, 2)
    hr = np.asarray(hero_rank, dtype=np.int64)
    orr = np.asarray(opp_rank, dtype=np.int64)
    if kernel == "auto":
        kernel = "dense" if max(len(hr), len(orr)) <= 400 else "sorted"
    if kernel == "dense":
        return DenseKernel.exact(hc, hr, oc, orr, dtype)
    return SortedKernel(hc, hr, oc, orr, dtype)


def make_solver(spot: RiverSpot, hero_cards, hero_w, hero_rank, opp_cards, opp_w, opp_rank,
                cfg: TreeCfg = TreeCfg(), kernel: str = "auto", dtype=np.float32,
                track_all: bool = False) -> RiverSolver:
    k = make_kernel(hero_cards, hero_rank, opp_cards, opp_rank, kernel, dtype)
    return RiverSolver(spot, hero_w, opp_w, k, cfg, dtype, track_all)


# time left after the ranges (s) -> buckets per player; set from the box-size curve in docs/reports/TIER4_RIVER.md
AUTO_BUCKETS = ((0.012, 48), (0.06, 64), (INF, 96))


def auto_buckets(time_left_s: float) -> int:
    return next(b for t, b in AUTO_BUCKETS if time_left_s < t)


def build_game(spot: RiverSpot, hero_cards, hero_w, hero_rank, opp_cards, opp_w, opp_rank, hero_index: int,
               cfg: TreeCfg = TreeCfg(), dtype=np.float32, buckets: int = 0, kernel: str = "auto",
               track_all: bool = False, card_removal: bool = False, auto: bool = False,
               time_left: float = 0.0):
    """The solver for one spot, and what a caller needs to read it: (solver, our index in its
    game, (hero bucket ids, opp bucket ids) or None when it plays exact combos). See solve_river."""
    hr = np.asarray(hero_rank, dtype=np.int64)
    orr = np.asarray(opp_rank, dtype=np.int64)
    hw = np.asarray(hero_w, dtype=np.float64)
    ow = np.asarray(opp_w, dtype=np.float64)
    idx = hero_index
    if auto:
        keep_h = hw > 0
        keep_h[hero_index] = True
        keep_o = ow > 0
        if not (keep_h.all() and keep_o.all()):
            idx = int(keep_h[:hero_index].sum())
            hero_cards, hr, hw = np.asarray(hero_cards)[keep_h], hr[keep_h], hw[keep_h]
            opp_cards, orr, ow = np.asarray(opp_cards)[keep_o], orr[keep_o], ow[keep_o]
        buckets = auto_buckets(time_left)
        card_removal = True
        dtype = np.float64            # float32 is no faster at these sizes and hits denormals (up to 3x slower on 5-8 % of spots)
        if max(len(hw), len(ow)) <= buckets:
            buckets, kernel = 0, "dense"
    if buckets > 0:
        hb, hbw = bucket_ranges(hr, hw, buckets)
        ob, obw = bucket_ranges(orr, ow, buckets)
        k = bucket_kernel(hr, hw, hb, orr, ow, ob, dtype,
                          hero_cards if card_removal else None, opp_cards if card_removal else None)
        return RiverSolver(spot, hbw, obw, k, cfg, dtype, track_all), int(hb[idx]), (hb, ob)
    return make_solver(spot, hero_cards, hw, hr, opp_cards, ow, orr, cfg, kernel, dtype, track_all), idx, None


def solve_river(spot: RiverSpot, hero_cards, hero_w, hero_rank, opp_cards, opp_w, opp_rank,
                hero_index: int, deadline: float, cfg: TreeCfg = TreeCfg(),
                max_iters: int = 10**9, min_iters: int = 0, keep_solver: bool = False,
                dtype=np.float32, buckets: int = 0, kernel: str = "auto",
                track_all: bool = False, card_removal: bool = False,
                auto: bool = False) -> Optional[SolveResult]:
    """Solve the river spot until `deadline` (a time.perf_counter() value) and return our
    root strategy for the hand at `hero_index` in `hero_cards`.

    buckets > 0   : play the bucketed game (that many strength buckets per player); the
                    strategy returned is that of our hand's bucket.
    card_removal  : bucketed game only: keep card removal at bucket level (see bucket_kernel).
    auto          : choose the best of all that for the time left (ignores `buckets`, `kernel`,
                    `card_removal`, `dtype`): combos with zero weight are dropped; if both ranges then
                    fit in the bucket count, the exact game (dense kernel); else bucketed with
                    card removal, buckets from `auto_buckets(time left)`.
    kernel        : see make_kernel (ignored when bucketing).
    Never runs past the deadline except for `min_iters` passes (default 0). Returns None when
    not a single pass fit (the caller falls back to its own river policy)."""
    t0 = time.perf_counter()
    s, idx, _ = build_game(spot, hero_cards, hero_w, hero_rank, opp_cards, opp_w, opp_rank, hero_index, cfg,
                           dtype, buckets, kernel, track_all, card_removal, auto, deadline - t0)
    t1 = time.perf_counter()
    if t1 >= deadline and min_iters <= 0:
        return None
    n = s.run(deadline, max_iters=max_iters, min_iters=min_iters)
    t2 = time.perf_counter()
    if n == 0:
        return None
    return SolveResult(s.tree.root_labels, s.root_strategy(idx), n, t1 - t0, t2 - t1,
                       s if keep_solver else None)


# ------------------------------------------------------------------ helpers for callers


def combos_excluding(dead: Sequence[int], n_cards: int = 52) -> np.ndarray:
    """All 2-card combos (i < j) of the deck that avoid every card in `dead`."""
    d = set(int(x) for x in dead)
    live = np.array([c for c in range(n_cards) if c not in d], dtype=np.int64)
    i, j = np.triu_indices(len(live), 1)
    return np.stack([live[i], live[j]], axis=1)


_RANKS: dict = {"ev": None, "board": None, "keys": np.zeros(0, np.int64), "val": np.zeros(0, np.int64)}


def hand_ranks(evaluator, combos: np.ndarray, board: Sequence[int]) -> np.ndarray:
    """Showdown value (higher wins) of each combo on the 5-card board, any 5 of the 7.

    Values are cached for the last board (and evaluator): our range and theirs overlap almost
    entirely, and a later river decision of the same hand has the same board, so each combo is
    evaluated once. Sorted keys + searchsorted, no per-combo Python."""
    combos = np.asarray(combos, dtype=np.int64)
    b = tuple(int(x) for x in board)
    c = _RANKS
    if c["ev"] is not evaluator or c["board"] != b:
        c.update(ev=evaluator, board=b, keys=np.zeros(0, np.int64), val=np.zeros(0, np.int64))
    keys = np.sort(combos, axis=1)
    keys = keys[:, 0] * 52 + keys[:, 1]
    pos = np.minimum(np.searchsorted(c["keys"], keys), max(len(c["keys"]) - 1, 0))
    hit = (c["keys"][pos] == keys) if len(c["keys"]) else np.zeros(len(keys), bool)
    if not hit.all():
        new_keys, first = np.unique(keys[~hit], return_index=True)
        new_val = np.asarray(evaluator.evaluate_batch(combos[~hit][first], np.asarray(b, dtype=np.intp)),
                             dtype=np.int64)
        allk = np.concatenate([c["keys"], new_keys])
        allv = np.concatenate([c["val"], new_val])
        o = np.argsort(allk, kind="stable")
        c["keys"], c["val"] = allk[o], allv[o]
        pos = np.searchsorted(c["keys"], keys)
    return c["val"][pos]
