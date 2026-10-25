"""External-sampling MCCFR with CFR+ style updates (lab only).

Game interface (two players, zero-sum):
    root(rng)                -> state         a fresh hand (chance sampled at the root)
    is_terminal(s)           -> bool
    utility(s, p)            -> float         player p's payoff at a terminal state
    to_act(s)                -> int | None    player to act, None for a chance node
    chance(s, rng)           -> state         sample one chance outcome (for mid-game chance)
    actions(s)               -> list          abstract action ids legal here (>= 1)
    play(s, a)               -> state         child state (must not mutate s)
    infoset(s, p)            -> hashable      what player p knows at s

Algorithm: for each iteration and each traverser p, sample chance and the opponent's
actions from the current strategy (with an exploration "trembling hand" epsilon), and
walk ALL of p's actions. Regrets are floored at 0 (regret-matching+); the average strategy
is weighted linearly by iteration (CFR+ averaging). Checkpoint with save()/load().
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Optional

import numpy as np


class MCCFR:
    # epsilon > 0 samples opponent actions off-policy WITHOUT importance correction: this
    # biases the solution (Phase 23: on Leduc, eps=0.05 stalls at ~0.063 exploitability
    # while eps=0 keeps falling to 0.020 at 10^6 iterations). Keep 0 unless you know why.
    def __init__(self, game, seed: int = 0, epsilon: float = 0.0) -> None:
        self.game = game
        self.rng = np.random.default_rng(seed)
        self.epsilon = epsilon                 # trembling hand for sampled opponent actions
        self.regret: dict = {}                 # infoset -> np.ndarray
        self.avg: dict = {}                    # infoset -> np.ndarray (weighted strategy sum)
        self.iterations = 0
        self.visits: dict = {}                 # infoset -> traverser visits (diagnostics)

    # ---- strategy
    def strategy(self, key, n: int) -> np.ndarray:
        r = self.regret.get(key)
        if r is None:
            return np.full(n, 1.0 / n)
        pos = np.maximum(r, 0.0)
        s = pos.sum()
        return pos / s if s > 0 else np.full(n, 1.0 / n)

    def average_strategy(self, key, n: int) -> np.ndarray:
        a = self.avg.get(key)
        if a is None or a.sum() <= 0:
            return np.full(n, 1.0 / n)
        return a / a.sum()

    # ---- traversal
    def traverse(self, s, p: int) -> float:
        g = self.game
        if g.is_terminal(s):
            return g.utility(s, p)
        q = g.to_act(s)
        if q is None:
            return self.traverse(g.chance(s, self.rng), p)
        acts = g.actions(s)
        n = len(acts)
        key = g.infoset(s, q)
        sigma = self.strategy(key, n)
        if q == p:
            vals = np.array([self.traverse(g.play(s, a), p) for a in acts])
            node = float(sigma @ vals)
            r = self.regret.setdefault(key, np.zeros(n))
            self.visits[key] = self.visits.get(key, 0) + 1
            r += vals - node
            np.maximum(r, 0.0, out=r)                       # CFR+: no negative regrets
            return node
        # Opponent node: sample one action; accumulate the average strategy (linear weights).
        avg = self.avg.setdefault(key, np.zeros(n))
        avg += (self.iterations + 1) * sigma
        probs = (1 - self.epsilon) * sigma + self.epsilon / n
        i = int(self.rng.choice(n, p=probs))
        return self.traverse(g.play(s, acts[i]), p)

    def iterate(self, n: int = 1) -> None:
        for _ in range(n):
            for p in (0, 1):
                self.traverse(self.game.root(self.rng), p)
            self.iterations += 1

    # ---- checkpoints
    def save(self, path) -> None:
        with open(path, "wb") as f:
            pickle.dump({"regret": self.regret, "avg": self.avg, "iterations": self.iterations,
                         "rng": self.rng.bit_generator.state, "visits": self.visits}, f)

    @staticmethod
    def load(path, game, epsilon: float = 0.0) -> "MCCFR":
        m = MCCFR(game, epsilon=epsilon)
        with open(path, "rb") as f:
            d = pickle.load(f)
        m.regret, m.avg, m.iterations = d["regret"], d["avg"], d["iterations"]
        m.rng.bit_generator.state = d["rng"]
        m.visits = d.get("visits", {})
        return m


def expected_value(game, policy, p: int = 0, samples: Optional[int] = None, rng=None) -> float:
    """Exact (enumerating chance via game.chance_outcomes) or sampled value of `policy`
    (infoset, n -> probabilities) for player p, both players following it."""
    def walk(s, prob=1.0):
        if game.is_terminal(s):
            return game.utility(s, p)
        q = game.to_act(s)
        acts = game.actions(s)
        sigma = policy(game.infoset(s, q), len(acts))
        return sum(sigma[i] * walk(game.play(s, a)) for i, a in enumerate(acts) if sigma[i] > 0)
    outcomes = getattr(game, "chance_outcomes", None)
    if outcomes is not None:
        return sum(w * walk(s) for s, w in outcomes())
    rng = rng or np.random.default_rng(0)
    return float(np.mean([walk(game.root(rng)) for _ in range(samples or 10000)]))


def export_uint8(solver: MCCFR, min_visits: float = 0.0, min_traverser_visits: int = 0) -> dict:
    """Average strategies quantized to uint8 (sum 255), pruning infosets that are uniform
    (no information), whose average weight is <= `min_visits` (note: weights grow with the
    iteration number, so this barely prunes anything in a long run), or that the traverser
    visited fewer than `min_traverser_visits` times (undertrained; the bot falls back)."""
    out = {}
    for key, a in solver.avg.items():
        total = a.sum()
        if total <= min_visits:
            continue
        if min_traverser_visits and solver.visits.get(key, 0) < min_traverser_visits:
            continue
        p = a / total
        if np.allclose(p, 1.0 / len(p), atol=1e-3):
            continue
        q = np.floor(p * 255).astype(np.int32)
        q[np.argmax(p)] += 255 - q.sum()
        out[key] = q.astype(np.uint8)
    return out


def save_strategy(table: dict, path) -> None:
    Path(path).write_bytes(pickle.dumps(table))


def exploitability(game, policy) -> float:
    """Exact exploitability for small games with game.chance_outcomes(): the average over
    both players of (best-response value - value of `policy`), via pure-strategy
    enumeration of the best responder's infosets (fine for Kuhn-sized games)."""
    import itertools

    def infosets_of(p):
        found = {}

        def walk(s):
            if game.is_terminal(s):
                return
            q = game.to_act(s)
            acts = game.actions(s)
            if q == p:
                found[game.infoset(s, p)] = len(acts)
            for a in acts:
                walk(game.play(s, a))
        for s, _ in game.chance_outcomes():
            walk(s)
        return found

    def value(p, pure):
        def walk(s):
            if game.is_terminal(s):
                return game.utility(s, p)
            q = game.to_act(s)
            acts = game.actions(s)
            key = game.infoset(s, q)
            if q == p:
                return walk(game.play(s, acts[pure[key]]))
            sigma = policy(key, len(acts))
            return sum(sigma[i] * walk(game.play(s, a)) for i, a in enumerate(acts) if sigma[i] > 0)
        return sum(w * walk(s) for s, w in game.chance_outcomes())

    gaps = []
    for p in (0, 1):
        sets = infosets_of(p)
        keys = list(sets)
        best = max(value(p, dict(zip(keys, choice)))
                   for choice in itertools.product(*(range(sets[k]) for k in keys)))
        gaps.append(best - expected_value(game, policy, p))
    return sum(gaps) / 2
