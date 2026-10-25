"""Exact policy evaluation and best response for small two-player zero-sum games.

Works with any game that implements the solver interface (lab/cfr/mccfr.py) plus
    chance_outcomes()      -> iterable of (root state, probability)
    chance_children(s)     -> list of (state, probability) at a mid-game chance node
                              (only needed if to_act(s) can return None)
The full game tree is built once (fine for Kuhn / Leduc sized games, ~10^4-10^5 nodes),
then any tabular policy `policy(infoset, n_actions) -> probabilities` can be evaluated.

Exploitability = (BR_0(policy) + BR_1(policy)) / 2, the average amount a best-responding
opponent wins per game against `policy` (0 exactly at a Nash equilibrium).
"""
from __future__ import annotations

from typing import Callable

import numpy as np

Policy = Callable[[object, int], np.ndarray]

TERMINAL, CHANCE, DECISION = 0, 1, 2


class Tree:
    """Flat game tree: node i has kind[i], player[i], key[i] (actor's infoset),
    children[i] (list of node ids), probs[i] (chance probabilities) and u0[i]
    (player 0's payoff at terminals). `roots` = [(node, probability)]."""

    def __init__(self, game) -> None:
        self.kind: list[int] = []
        self.player: list[int] = []
        self.key: list = []
        self.children: list[list[int]] = []
        self.probs: list[list[float]] = []
        self.u0: list[float] = []
        self.roots = [(self._build(game, s), w) for s, w in game.chance_outcomes()]

    def _new(self, kind, player=-1, key=None, u0=0.0) -> int:
        self.kind.append(kind)
        self.player.append(player)
        self.key.append(key)
        self.children.append([])
        self.probs.append([])
        self.u0.append(u0)
        return len(self.kind) - 1

    def _build(self, game, s) -> int:
        if game.is_terminal(s):
            return self._new(TERMINAL, u0=game.utility(s, 0))
        q = game.to_act(s)
        if q is None:
            i = self._new(CHANCE)
            for child, w in game.chance_children(s):
                self.children[i].append(self._build(game, child))
                self.probs[i].append(w)
            return i
        i = self._new(DECISION, q, game.infoset(s, q))
        for a in game.actions(s):
            self.children[i].append(self._build(game, game.play(s, a)))
        return i

    @property
    def size(self) -> int:
        return len(self.kind)

    def infosets(self, p: int) -> dict:
        """infoset key -> number of actions, for player p."""
        return {self.key[i]: len(self.children[i]) for i in range(self.size)
                if self.kind[i] == DECISION and self.player[i] == p}


def _cached(policy: Policy) -> Policy:
    memo: dict = {}

    def f(key, n):
        k = (key, n)
        if k not in memo:
            memo[k] = np.asarray(policy(key, n), dtype=float)
        return memo[k]
    return f


def expected_value(tree: Tree, policy: Policy, p: int = 0) -> float:
    """Player p's expected payoff when both players follow `policy`."""
    pol = _cached(policy)
    sign = 1.0 if p == 0 else -1.0

    def val(i: int) -> float:
        k = tree.kind[i]
        if k == TERMINAL:
            return sign * tree.u0[i]
        if k == CHANCE:
            return sum(w * val(c) for c, w in zip(tree.children[i], tree.probs[i]))
        kids = tree.children[i]
        sigma = pol(tree.key[i], len(kids))
        return sum(sigma[j] * val(c) for j, c in enumerate(kids) if sigma[j] > 0)
    return sum(w * val(r) for r, w in tree.roots)


def best_response_value(tree: Tree, policy: Policy, p: int) -> float:
    """Value for player p of a best response to `policy` (the other player's part)."""
    pol = _cached(policy)
    sign = 1.0 if p == 0 else -1.0
    n = tree.size
    reach = np.zeros(n)                     # opponent x chance reach of every node
    members: dict = {}                      # p's infoset -> its nodes

    stack = [(r, w) for r, w in tree.roots]
    while stack:
        i, pr = stack.pop()
        reach[i] += pr
        k = tree.kind[i]
        kids = tree.children[i]
        if k == CHANCE:
            stack.extend((c, pr * w) for c, w in zip(kids, tree.probs[i]))
        elif k == DECISION:
            if tree.player[i] == p:
                members.setdefault(tree.key[i], []).append(i)
                stack.extend((c, pr) for c in kids)
            else:
                sigma = pol(tree.key[i], len(kids))
                stack.extend((c, pr * sigma[j]) for j, c in enumerate(kids))

    best: dict = {}
    memo: dict = {}

    def choose(key) -> int:
        a = best.get(key)
        if a is None:
            nodes = members[key]
            m = len(tree.children[nodes[0]])
            totals = [sum(reach[i] * val(tree.children[i][j]) for i in nodes) for j in range(m)]
            a = best[key] = int(np.argmax(totals))
        return a

    def val(i: int) -> float:
        v = memo.get(i)
        if v is not None:
            return v
        k = tree.kind[i]
        kids = tree.children[i]
        if k == TERMINAL:
            v = sign * tree.u0[i]
        elif k == CHANCE:
            v = sum(w * val(c) for c, w in zip(kids, tree.probs[i]))
        elif tree.player[i] == p:
            v = val(kids[choose(tree.key[i])])
        else:
            sigma = pol(tree.key[i], len(kids))
            v = sum(sigma[j] * val(c) for j, c in enumerate(kids) if sigma[j] > 0)
        memo[i] = v
        return v

    return sum(w * val(r) for r, w in tree.roots)


def exploitability(tree: Tree, policy: Policy) -> float:
    """(BR_0 + BR_1) / 2: 0 at equilibrium, > 0 otherwise (game units per game)."""
    return 0.5 * (best_response_value(tree, policy, 0) + best_response_value(tree, policy, 1))


def solve_cfr_plus(tree: Tree, iterations: int) -> Callable[[object, int], np.ndarray]:
    """Full-width CFR+ on the whole tree (alternating updates, linear averaging).
    A reference solver for small games: returns the average policy."""
    regret: dict = {}
    avg: dict = {}
    delta: dict = {}

    def sigma(key, m):
        r = regret.get(key)
        if r is None:
            return np.full(m, 1.0 / m)
        pos = np.maximum(r, 0.0)
        s = pos.sum()
        return pos / s if s > 0 else np.full(m, 1.0 / m)

    def walk(i, p, pi_p, pi_o, t):
        k = tree.kind[i]
        if k == TERMINAL:
            return tree.u0[i] if p == 0 else -tree.u0[i]
        kids = tree.children[i]
        if k == CHANCE:
            return sum(w * walk(c, p, pi_p, pi_o * w, t) for c, w in zip(kids, tree.probs[i]))
        key, m = tree.key[i], len(kids)
        s = sigma(key, m)
        if tree.player[i] == p:
            vals = np.array([walk(c, p, pi_p * s[j], pi_o, t) for j, c in enumerate(kids)])
            node = float(s @ vals)
            # buffered: the strategy must stay fixed for the whole pass
            delta.setdefault(key, np.zeros(m))[:] += pi_o * (vals - node)
            avg.setdefault(key, np.zeros(m))[:] += t * pi_p * s
            return node
        return sum(s[j] * walk(c, p, pi_p, pi_o * s[j], t) for j, c in enumerate(kids) if s[j] > 0)

    for t in range(1, iterations + 1):
        for p in (0, 1):
            delta.clear()
            for r, w in tree.roots:
                walk(r, p, 1.0, w, t)
            for key, d in delta.items():
                r = regret.setdefault(key, np.zeros(len(d)))
                np.maximum(r + d, 0.0, out=r)

    def policy(key, m):
        a = avg.get(key)
        if a is None or a.sum() <= 0:
            return np.full(m, 1.0 / m)
        return a / a.sum()
    return policy
