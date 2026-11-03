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


# ------------------------------------------------------------------ card-removal terminals


class _Dir:
    """Index arrays for 'values of a-hands from a reach vector over b-hands'."""

    def __init__(self, rank_a, cards_a, rank_b, cards_b) -> None:
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
            # S_c = C[lo] + C[hi] - C[st] - C[en] (block 2 offsets), subtracted from S_all
            minus += [b2 + lo_c, b2 + hi_c]
            plus += [b2 + st, b2 + en]
        self.plus = np.stack(plus).astype(np.intp)       # (6, na)
        self.minus = np.stack(minus).astype(np.intp)     # (5, na)
        self.order_b = order_b.astype(np.intp)
        self.perm_e = perm_e.astype(np.intp)
        self.width = 1 + nb + 1 + 2 * nb
        # fold: sum over compatible = total - cs[c1] - cs[c2] + z[same]
        inc = np.zeros((nb, 52), dtype=np.float64)
        inc[np.arange(nb), cards_b[:, 0]] = 1.0
        inc[np.arange(nb), cards_b[:, 1]] = 1.0
        self.inc = inc
        self.c1 = cards_a[:, 0].astype(np.intp)
        self.c2 = cards_a[:, 1].astype(np.intp)
        lookup = {}
        for j in range(nb):
            a_, b_ = int(cards_b[j, 0]), int(cards_b[j, 1])
            lookup[(a_, b_)] = lookup[(b_, a_)] = j
        same = np.array([lookup.get((int(cards_a[i, 0]), int(cards_a[i, 1])), -1) for i in range(na)])
        self.same = np.maximum(same, 0).astype(np.intp)
        self.same_mask = (same >= 0).astype(np.float64)

    def show(self, z: np.ndarray, buf: np.ndarray) -> np.ndarray:
        """z (T, nb) -> (T, na): sum_j z_j sign(rank_i - rank_j) over compatible j."""
        nb = self.nb
        buf[:, 0] = 0.0
        buf[:, 1:nb + 1] = z[:, self.order_b]
        buf[:, nb + 1] = 0.0
        buf[:, nb + 2:] = z[:, self.perm_e]
        np.cumsum(buf, axis=1, out=buf)
        return buf[:, self.plus].sum(axis=1) - buf[:, self.minus].sum(axis=1)

    def fold(self, z: np.ndarray) -> np.ndarray:
        """z (T, nb) -> (T, na): sum_j z_j over compatible j."""
        cs = z @ self.inc
        return (z.sum(axis=1, keepdims=True) - cs[:, self.c1] - cs[:, self.c2]
                + z[:, self.same] * self.same_mask)


# ------------------------------------------------------------------ the solver


class RiverSolver:
    """State of one solve. Build it (setup cost), then `run(deadline)`; read the result."""

    def __init__(self, spot: RiverSpot, hero_cards, hero_w, hero_rank, opp_cards, opp_w, opp_rank,
                 cfg: TreeCfg = TreeCfg(), dtype=np.float64) -> None:
        self.dt = dtype
        self.tree = t = Tree(spot, cfg)
        self.n0, self.n1 = len(hero_w), len(opp_w)
        hc = np.asarray(hero_cards, dtype=np.int64).reshape(-1, 2)
        oc = np.asarray(opp_cards, dtype=np.int64).reshape(-1, 2)
        hr = np.asarray(hero_rank, dtype=np.int64)
        orr = np.asarray(opp_rank, dtype=np.int64)
        self.hero_cards, self.opp_cards = hc, oc
        w0 = np.asarray(hero_w, dtype=np.float64)
        w1 = np.asarray(opp_w, dtype=np.float64)
        self.w0 = (w0 / w0.sum()).astype(dtype)
        self.w1 = (w1 / w1.sum()).astype(dtype)
        self.d0 = _Dir(hr, hc, orr, oc)       # hero values from opp reach
        self.d1 = _Dir(orr, oc, hr, hc)       # opp values from hero reach
        V = t.n
        self.V = V
        kinds = np.array(t.kind)
        self.fold_ids = np.nonzero(kinds == 1)[0]
        self.show_ids = np.nonzero(kinds == 2)[0]
        term = np.array(t.term, dtype=np.float64)
        self.fold_c0 = term[self.fold_ids, 0, None].astype(dtype)
        self.fold_c1 = term[self.fold_ids, 1, None].astype(dtype)
        self.show_c = term[self.show_ids, 0, None].astype(dtype)
        self.buf0 = np.zeros((len(self.show_ids), self.d0.width), dtype=dtype)
        self.buf1 = np.zeros((len(self.show_ids), self.d1.width), dtype=dtype)
        # decision nodes per depth; strategy tensors per player
        self.K = max(len(c) for c in t.children if c)
        self.dec_by_depth: list[list[int]] = [[] for _ in range(t.max_depth + 1)]
        for i in t.dec_ids:
            self.dec_by_depth[t.depth[i]].append(i)
        self.pidx = {0: {}, 1: {}}                 # node id -> row in that player's tensors
        for p in (0, 1):
            ids = [i for i in t.dec_ids if t.depth[i] % 2 == p]
            self.pidx[p] = {n: r for r, n in enumerate(ids)}
        self.player_nodes = {p: np.array(list(self.pidx[p]), dtype=np.intp) for p in (0, 1)}
        n_hand = {0: self.n0, 1: self.n1}
        self.R, self.A, self.mask, self.unif, self.child_idx = {}, {}, {}, {}, {}
        for p in (0, 1):
            ids = list(self.pidx[p])
            D = len(ids)
            m = np.zeros((D, self.K, 1), dtype=dtype)
            ch = np.full((D, self.K), V, dtype=np.intp)        # V = the all-zero dummy row
            for r, n in enumerate(ids):
                for k, c in enumerate(t.children[n]):
                    m[r, k, 0] = 1.0
                    ch[r, k] = c
            self.mask[p] = m
            self.child_idx[p] = ch
            self.R[p] = np.zeros((D, self.K, n_hand[p]), dtype=dtype)
            self.A[p] = np.zeros((D, self.K, n_hand[p]), dtype=dtype)
            self.unif[p] = m / np.maximum(m.sum(axis=1, keepdims=True), 1.0)
        # per depth: block of children, the parent rows, slots, reduceat starts
        self.levels = []
        for d in range(t.max_depth):
            ids = self.dec_by_depth[d]
            if not ids:
                continue
            cs, ce = t.block[d + 1]
            p = d % 2
            rows = np.array([self.pidx[p][n] for n in ids], dtype=np.intp)
            # children of decision node n are contiguous; the block holds only children of
            # this depth's decisions, in parent order
            starts = np.array([t.children[n][0] - cs for n in ids], dtype=np.intp)
            par = np.array([t.parent[c] for c in range(cs, ce)], dtype=np.intp)
            slot = np.array([t.slot[c] for c in range(cs, ce)], dtype=np.intp)
            prow = np.array([self.pidx[p][n] for n in par], dtype=np.intp)
            self.levels.append((d, p, np.array(ids, dtype=np.intp), cs, ce, par, prow, slot, starts))
        self.iterations = 0
        self.setup_done = time.perf_counter()

    # ---- one pass
    def _strategy(self, p: int) -> np.ndarray:
        R = self.R[p]
        pos = (R + 1e-30) * self.mask[p]
        return pos / pos.sum(axis=1, keepdims=True)

    def step(self) -> None:
        t, V, dt = self.tree, self.V, self.dt
        S = {0: self._strategy(0), 1: self._strategy(1)}
        Q = {0: np.zeros((V + 1, self.n0), dtype=dt), 1: np.zeros((V + 1, self.n1), dtype=dt)}
        Val = {0: np.zeros((V + 1, self.n0), dtype=dt), 1: np.zeros((V + 1, self.n1), dtype=dt)}
        Q[0][0] = self.w0
        Q[1][0] = self.w1
        blocks = []
        for (d, p, ids, cs, ce, par, prow, slot, starts) in self.levels:
            o = 1 - p
            sb = S[p][prow, slot]                               # (children, n_p)
            Q[p][cs:ce] = Q[p][par] * sb
            Q[o][cs:ce] = Q[o][par]
            blocks.append(sb)
        # terminals
        if len(self.fold_ids):
            z1 = Q[1][self.fold_ids]
            z0 = Q[0][self.fold_ids]
            Val[0][self.fold_ids] = self.fold_c0 * self.d0.fold(z1)
            Val[1][self.fold_ids] = self.fold_c1 * self.d1.fold(z0)
        if len(self.show_ids):
            z1 = Q[1][self.show_ids]
            z0 = Q[0][self.show_ids]
            Val[0][self.show_ids] = self.show_c * self.d0.show(z1, self.buf0)
            Val[1][self.show_ids] = self.show_c * self.d1.show(z0, self.buf1)
        # backward
        for lv, sb in zip(reversed(self.levels), reversed(blocks)):
            (d, p, ids, cs, ce, par, prow, slot, starts) = lv
            o = 1 - p
            Val[p][ids] = np.add.reduceat(Val[p][cs:ce] * sb, starts, axis=0)
            Val[o][ids] = np.add.reduceat(Val[o][cs:ce], starts, axis=0)
        # regrets and average strategy
        w = float(self.iterations + 1)
        for p in (0, 1):
            nodes = self.player_nodes[p]
            if not len(nodes):
                continue
            cv = Val[p][self.child_idx[p]]                      # (D, K, n_p)
            inst = (cv - Val[p][nodes][:, None, :]) * self.mask[p]
            np.maximum(self.R[p] + inst, 0.0, out=self.R[p])
            self.A[p] += (w * Q[p][nodes])[:, None, :] * S[p]
        self.iterations += 1

    def run(self, deadline: float, max_iters: int = 10**9, min_iters: int = 0) -> int:
        """Iterate until `deadline` (a perf_counter value) or `max_iters`. Returns the count."""
        n = 0
        while n < max_iters and (n < min_iters or time.perf_counter() < deadline):
            self.step()
            n += 1
        return n

    # ---- results
    def average(self, p: int) -> np.ndarray:
        """Average strategy (D, K, n_p) for player p, rows in `player_nodes[p]` order."""
        A = self.A[p]
        tot = A.sum(axis=1, keepdims=True)
        out = np.where(tot > 0, A / np.maximum(tot, 1e-300), self.unif[p])
        return out

    def root_strategy(self, hero_index: int) -> np.ndarray:
        """Average strategy at the root for our hand `hero_index`, over `tree.root_labels`."""
        a = self.average(0)
        r = self.pidx[0][0]
        k = len(self.tree.children[0])
        return a[r, :k, hero_index].astype(np.float64)

    def exploitability(self) -> float:
        """(BR_0 + BR_1) / 2 of the average strategy, in pot units (one pot = 1.0), by a
        vector best response over the same tree. 0 at equilibrium."""
        t, V, dt = self.tree, self.V, np.float64
        avg = {p: self.average(p).astype(dt) for p in (0, 1)}
        # reach of each player under the AVERAGE strategies
        Q = {0: np.zeros((V + 1, self.n0)), 1: np.zeros((V + 1, self.n1))}
        Q[0][0] = self.w0
        Q[1][0] = self.w1
        for (d, p, ids, cs, ce, par, prow, slot, starts) in self.levels:
            o = 1 - p
            Q[p][cs:ce] = Q[p][par] * avg[p][prow, slot]
            Q[o][cs:ce] = Q[o][par]
        total = 0.0
        z_norm = float(self.d0.fold(self.w1[None, :].astype(dt))[0] @ self.w0.astype(dt))
        for br in (0, 1):
            o = 1 - br
            Val = {br: np.zeros((V + 1, self.n0 if br == 0 else self.n1))}
            dirn = self.d0 if br == 0 else self.d1
            coef_f = self.fold_c0 if br == 0 else self.fold_c1
            if len(self.fold_ids):
                Val[br][self.fold_ids] = coef_f.astype(dt) * dirn.fold(Q[o][self.fold_ids])
            if len(self.show_ids):
                buf = np.zeros((len(self.show_ids), dirn.width))
                Val[br][self.show_ids] = self.show_c.astype(dt) * dirn.show(Q[o][self.show_ids], buf)
            for (d, p, ids, cs, ce, par, prow, slot, starts) in reversed(self.levels):
                if p == br:
                    Val[br][ids] = np.maximum.reduceat(Val[br][cs:ce], starts, axis=0)
                else:
                    Val[br][ids] = np.add.reduceat(Val[br][cs:ce], starts, axis=0)
            w = self.w0 if br == 0 else self.w1
            total += float(Val[br][0] @ w.astype(dt))
        return 0.5 * total / z_norm


@dataclass
class SolveResult:
    labels: list                 # root actions: (kind, level) -- level = our street total for a raise
    probs: np.ndarray            # our average strategy at the root for our actual hand
    iterations: int
    setup_s: float
    run_s: float
    solver: Optional[RiverSolver] = None


def solve_river(spot: RiverSpot, hero_cards, hero_w, hero_rank, opp_cards, opp_w, opp_rank,
                hero_index: int, deadline: float, cfg: TreeCfg = TreeCfg(),
                max_iters: int = 10**9, min_iters: int = 1, keep_solver: bool = False,
                dtype=np.float64) -> Optional[SolveResult]:
    """Solve the river spot until `deadline` (a time.perf_counter() value) and return our
    root strategy for the hand at `hero_index` in `hero_cards`. Returns None when setup alone
    would pass the deadline (the caller falls back). Never runs past the deadline except for
    `min_iters` iterations when asked."""
    t0 = time.perf_counter()
    s = RiverSolver(spot, hero_cards, hero_w, hero_rank, opp_cards, opp_w, opp_rank, cfg, dtype)
    t1 = time.perf_counter()
    if t1 >= deadline and min_iters <= 0:
        return None
    n = s.run(deadline, max_iters=max_iters, min_iters=min_iters)
    t2 = time.perf_counter()
    return SolveResult(s.tree.root_labels, s.root_strategy(hero_index), n, t1 - t0, t2 - t1,
                       s if keep_solver else None)


# ------------------------------------------------------------------ helpers for callers


def combos_excluding(dead: Sequence[int], n_cards: int = 52) -> np.ndarray:
    """All 2-card combos (i < j) of the deck that avoid every card in `dead`."""
    live = np.array([c for c in range(n_cards) if c not in set(int(x) for x in dead)], dtype=np.int64)
    i, j = np.triu_indices(len(live), 1)
    return np.stack([live[i], live[j]], axis=1)


def hand_ranks(evaluator, combos: np.ndarray, board: Sequence[int]) -> np.ndarray:
    """Showdown value (higher wins) of each combo on the 5-card board, any 5 of the 7."""
    return np.asarray(evaluator.evaluate_batch(combos, np.asarray(board, dtype=np.intp)), dtype=np.int64)
