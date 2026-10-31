"""Small games as flat trees, to validate the fast trainer (lab/cfr/fast/mccfr.py) exactly.

Kuhn poker: cards 0 < 1 < 2, ante 1 each, seat 0 acts first; check/bet 1, fold/call.
Its equilibrium value for seat 0 is -1/18.
"""
from __future__ import annotations

import itertools

import numpy as np

from lab.cfr.fast.mccfr import Game

KUHN_VALUE = -1.0 / 18.0


def kuhn() -> Game:
    # nodes, breadth first: 0 root (P0), 1 P1 after check, 2 P1 after bet, 3 check-check showdown,
    # 4 P0 after check-bet, 5 P1 folds, 6 bet-call showdown, 7 P0 folds, 8 check-bet-call showdown
    flat = {
        "kind": np.array([0, 0, 0, 2, 0, 1, 2, 1, 2]),
        "street": np.zeros(9, dtype=np.int64),
        "actor": np.array([0, 1, 1, -1, 0, -1, -1, -1, -1]),
        "hist": np.array([0, 1, 2, -1, 3, -1, -1, -1, -1]),
        "n_act": np.array([2, 2, 2, 0, 2, 0, 0, 0, 0]),
        "first": np.array([0, 2, 4, -1, 6, -1, -1, -1, -1]),
        "child": np.arange(1, 9),
        "contrib": np.array([[1, 1], [1, 1], [2, 1], [1, 1], [1, 2], [2, 1], [2, 2], [1, 2], [2, 2]]),
        "folder": np.array([-1, -1, -1, -1, -1, 1, -1, 0, -1]),
        "histories": [["", "C", "B", "CB"]],
    }
    deals = list(itertools.permutations(range(3), 2))
    buckets = np.array([[[a], [b]] for a, b in deals])
    showdown = np.array([1 if a > b else -1 for a, b in deals])
    return Game.from_flat(flat, [3], buckets, showdown)
