"""External-sampling MCCFR over a flat abstract tree (build map C3; Numba, lab only).

The game is given as `tree.flatten`-style arrays plus a deal pool: per deal, each seat's bucket on
every street and the showdown result. One iteration samples a deal and a traverser, walks every
traverser action and samples one action at the other player's nodes (external sampling). Iterations
run in parallel without locks ("hogwild": rare lost updates are harmless noise). Linear CFR is
applied by discounting regrets and strategy sums between batches (t / (t + 1)), as in Pluribus.

Rows: row(street, history id, bucket) = offset[street] + hist * n_buckets[street] + bucket
(docs/cfr/ABSTRACTION_V1.md section 3). Exact evaluation (profile value, best response,
exploitability) over an enumerated set of deals is in `exact_values`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit, prange

MAX_ACT = 6
MAX_DEPTH = 64
# The recursive traversal and its callers are not cached on disk: Numba's cache can load a stale
# self-recursive function (seen here as a segfault on the real tree after a Kuhn run).


@dataclass
class Game:
    """A flat tree + deals, ready for the trainer."""
    kind: np.ndarray
    street: np.ndarray
    actor: np.ndarray
    hist: np.ndarray
    n_act: np.ndarray
    first: np.ndarray
    child: np.ndarray
    contrib: np.ndarray
    folder: np.ndarray
    n_buckets: np.ndarray          # per street
    offset: np.ndarray             # per street
    rows: int
    buckets: np.ndarray            # (D, 2, n_streets) int16
    showdown: np.ndarray           # (D,) int8: +1 seat 0 wins, -1 seat 1 wins, 0 split
    histories: list

    @classmethod
    def from_flat(cls, flat: dict, n_buckets, buckets: np.ndarray, showdown: np.ndarray) -> "Game":
        n_hist = np.array([len(h) for h in flat["histories"]], dtype=np.int64)
        nb = np.asarray(n_buckets, dtype=np.int64)
        offset = np.concatenate([[0], np.cumsum(n_hist * nb)[:-1]]).astype(np.int64)
        return cls(flat["kind"].astype(np.int64), flat["street"].astype(np.int64),
                   flat["actor"].astype(np.int64), flat["hist"].astype(np.int64),
                   flat["n_act"].astype(np.int64), flat["first"].astype(np.int64),
                   flat["child"].astype(np.int64), flat["contrib"].astype(np.float64),
                   flat["folder"].astype(np.int64), nb, offset, int((n_hist * nb).sum()),
                   np.ascontiguousarray(buckets, dtype=np.int16),     # ids < 32768; 16 B per deal
                   np.ascontiguousarray(showdown, dtype=np.int8), flat["histories"])

    def arrays(self) -> tuple:
        return (self.kind, self.street, self.actor, self.hist, self.n_act, self.first, self.child,
                self.contrib, self.folder, self.n_buckets, self.offset, self.buckets, self.showdown)


@njit(cache=True, inline="always")
def _utility(n, p, sdv, contrib, folder, kind):
    if kind[n] == 1:                                   # fold
        q = folder[n]
        return -contrib[n, q] if p == q else contrib[n, q]
    win = sdv if p == 0 else -sdv
    if win > 0:
        return contrib[n, 1 - p]
    if win < 0:
        return -contrib[n, p]
    return 0.0


@njit(cache=False)
def _traverse(n, p, d, depth, kind, street, actor, hist, n_act, first, child, contrib, folder,
              n_buckets, offset, buckets, showdown, regret, ssum, visits, sig, util):
    if kind[n] != 0:
        return _utility(n, p, showdown[d], contrib, folder, kind)
    k = n_act[n]
    f = first[n]
    pl = actor[n]
    st = street[n]
    row = offset[st] + hist[n] * n_buckets[st] + buckets[d, pl, st]
    total = 0.0
    for a in range(k):
        r = regret[row, a]
        sig[depth, a] = r if r > 0.0 else 0.0
        total += sig[depth, a]
    if total > 0.0:
        for a in range(k):
            sig[depth, a] /= total
    else:
        for a in range(k):
            sig[depth, a] = 1.0 / k
    if pl == p:
        node = 0.0
        for a in range(k):
            u = _traverse(child[f + a], p, d, depth + 1, kind, street, actor, hist, n_act, first,
                          child, contrib, folder, n_buckets, offset, buckets, showdown, regret,
                          ssum, visits, sig, util)
            util[depth, a] = u
            node += sig[depth, a] * u
        for a in range(k):
            regret[row, a] += util[depth, a] - node
        visits[row] += 1
        return node
    for a in range(k):
        ssum[row, a] += sig[depth, a]
    x = np.random.random()
    a = 0
    acc = sig[depth, 0]
    while x >= acc and a < k - 1:
        a += 1
        acc += sig[depth, a]
    return _traverse(child[f + a], p, d, depth + 1, kind, street, actor, hist, n_act, first, child,
                     contrib, folder, n_buckets, offset, buckets, showdown, regret, ssum, visits, sig, util)


@njit(cache=False, parallel=True)
def run_batch(iters, start, kind, street, actor, hist, n_act, first, child, contrib, folder,
              n_buckets, offset, buckets, showdown, regret, ssum, visits, n_threads):
    """`iters` iterations (traverser alternates by iteration number). Returns nothing."""
    per = (iters + n_threads - 1) // n_threads
    for t in prange(n_threads):
        sig = np.empty((MAX_DEPTH, MAX_ACT))
        util = np.empty((MAX_DEPTH, MAX_ACT))
        lo = t * per
        hi = min(iters, lo + per)
        for it in range(lo, hi):
            d = np.random.randint(0, buckets.shape[0])
            _traverse(0, (start + it) & 1, d, 0, kind, street, actor, hist, n_act, first, child,
                      contrib, folder, n_buckets, offset, buckets, showdown, regret, ssum, visits, sig, util)


@njit(cache=False)
def run_serial(iters, start, kind, street, actor, hist, n_act, first, child, contrib, folder,
               n_buckets, offset, buckets, showdown, regret, ssum, visits):
    """As run_batch on one thread (reproducible with seed_rng)."""
    sig = np.empty((MAX_DEPTH, MAX_ACT))
    util = np.empty((MAX_DEPTH, MAX_ACT))
    for it in range(iters):
        d = np.random.randint(0, buckets.shape[0])
        _traverse(0, (start + it) & 1, d, 0, kind, street, actor, hist, n_act, first, child,
                  contrib, folder, n_buckets, offset, buckets, showdown, regret, ssum, visits, sig, util)


@njit(cache=True)
def seed_rng(seed):
    np.random.seed(seed)


@njit(cache=True, parallel=True)
def _seed_threads(seed, n):
    for t in prange(n):
        np.random.seed(seed + 7919 * t)


class Trainer:
    """Regrets and strategy sums over a Game; `train(iters)` in batches with Linear-CFR discounting."""

    def __init__(self, game: Game, seed: int = 0, threads: int = 1, lcfr_batches: int = 0) -> None:
        self.g = game
        self.regret = np.zeros((game.rows, MAX_ACT), dtype=np.float64)
        self.ssum = np.zeros((game.rows, MAX_ACT), dtype=np.float64)
        self.visits = np.zeros(game.rows, dtype=np.int64)          # traverser updates per row
        self.iterations = 0
        self.batches = 0
        self.threads = threads
        self.lcfr_batches = lcfr_batches        # discount after each of the first N batches
        seed_rng(seed)
        _seed_threads(seed, max(1, threads))

    def train(self, iters: int, batch: int = 0) -> None:
        batch = batch or iters
        done = 0
        while done < iters:
            m = min(batch, iters - done)
            if self.threads <= 1:
                run_serial(m, self.iterations, *self.g.arrays(), self.regret, self.ssum, self.visits)
            else:
                run_batch(m, self.iterations, *self.g.arrays(), self.regret, self.ssum, self.visits,
                          self.threads)
            self.iterations += m
            done += m
            self.batches += 1
            if self.batches <= self.lcfr_batches:
                w = self.batches / (self.batches + 1.0)
                self.regret *= w
                self.ssum *= w

    def state(self) -> dict:
        return {"regret": self.regret, "ssum": self.ssum, "visits": self.visits,
                "iterations": self.iterations, "batches": self.batches}

    def load_state(self, st) -> None:
        self.regret[...] = st["regret"]
        self.ssum[...] = st["ssum"]
        self.visits[...] = st["visits"]
        self.iterations, self.batches = int(st["iterations"]), int(st["batches"])

    def average(self) -> np.ndarray:
        """Average strategy per row (uniform over legal actions where nothing was accumulated)."""
        return normalize(self.ssum, self.g)


def legal_mask(game: Game) -> np.ndarray:
    """(rows, MAX_ACT) True for the actions that exist at each row's history."""
    mask = np.zeros((game.rows, MAX_ACT), dtype=bool)
    dec = game.kind == 0
    for n in np.nonzero(dec)[0]:
        st = game.street[n]
        base = game.offset[st] + game.hist[n] * game.n_buckets[st]
        mask[base: base + game.n_buckets[st], : game.n_act[n]] = True
    return mask


def normalize(table: np.ndarray, game: Game) -> np.ndarray:
    mask = legal_mask(game)
    t = np.where(mask, np.maximum(table, 0.0), 0.0)
    s = t.sum(axis=1, keepdims=True)
    uniform = mask / np.maximum(mask.sum(axis=1, keepdims=True), 1)
    return np.where(s > 0, t / np.where(s > 0, s, 1.0), uniform)


# --------------------------------------------------------------------------- exact evaluation

def exact_values(game: Game, strat: np.ndarray, weights: np.ndarray | None = None) -> dict:
    """Over the game's deals (weights: chance probabilities, default uniform):
    value of the profile for seat 0, each seat's best-response value, exploitability
    (mean of the two best-response values, in chips per hand). Python recursion, NumPy vectors."""
    g = game
    D = g.buckets.shape[0]
    w = np.full(D, 1.0 / D) if weights is None else np.asarray(weights, dtype=np.float64)

    def payoff(n, p):
        if g.kind[n] == 1:
            q = g.folder[n]
            v = -g.contrib[n, q] if p == q else g.contrib[n, q]
            return np.full(D, float(v))
        win = g.showdown if p == 0 else -g.showdown
        return np.where(win > 0, g.contrib[n, 1 - p], np.where(win < 0, -g.contrib[n, p], 0.0))

    def rows_of(n):
        st, pl = g.street[n], g.actor[n]
        return g.offset[st] + g.hist[n] * g.n_buckets[st] + g.buckets[:, pl, st]

    def value(n, p, reach_other, br):
        """Counterfactual value vector for p (weighted by chance x other's reach)."""
        if g.kind[n] != 0:
            return reach_other * payoff(n, p)
        k, f, pl = g.n_act[n], g.first[n], g.actor[n]
        rows = rows_of(n)
        if pl != p:
            out = np.zeros(D)
            for a in range(k):
                out += value(g.child[f + a], p, reach_other * strat[rows, a], br)
            return out
        vals = [value(g.child[f + a], p, reach_other, br) for a in range(k)]
        if not br:
            return sum(strat[rows, a] * vals[a] for a in range(k))
        st = g.street[n]
        b = g.buckets[:, pl, st]
        nb = int(g.n_buckets[st])
        totals = np.stack([np.bincount(b, weights=v, minlength=nb) for v in vals])   # (k, nb)
        best = np.argmax(totals, axis=0)
        return np.choose(best[b], vals)

    v0 = float(value(0, 0, w, False).sum())
    br0 = float(value(0, 0, w, True).sum())
    br1 = float(value(0, 1, w, True).sum())
    return {"value0": v0, "br0": br0, "br1": br1, "exploitability": (br0 + br1) / 2}


def export_uint8(avg: np.ndarray, game: Game, visits: np.ndarray, min_visits: int = 10) -> np.ndarray:
    """(rows, MAX_ACT) uint8 probabilities summing to 255 per row (export_uint8's rule in
    lab/cfr/mccfr.py: floor, remainder to the largest). Rows visited fewer than `min_visits` times
    by the traverser are all zero: the runtime treats them as a miss (contract section 3)."""
    q = np.floor(avg * 255).astype(np.int64)
    top = np.argmax(avg, axis=1)
    q[np.arange(len(q)), top] += 255 - q.sum(axis=1)
    q[visits < min_visits] = 0
    q[~legal_mask(game).any(axis=1)] = 0
    return q.astype(np.uint8)
