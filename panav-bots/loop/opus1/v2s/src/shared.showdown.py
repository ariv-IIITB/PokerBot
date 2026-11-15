"""Weighted showdown on a river board (BUILDMAP §7 Phase 2, §10).

For each of our hands h, the total range weight of opponent hands that h beats and ties,
excluding opponent hands that share a card with h or the board. Same sort + inclusion–exclusion
trick as features.all_features, with weights instead of counts. O(n log n), no 1326x1326 matrix.
"""
import numpy as np

from .cards import COMBO
from .evaluator import evaluate_board_plus


def river_values(board):
    """int64[1326] hand values on a 5-card board in idx2 order; -1 where the pair hits the board."""
    board = [int(c) for c in board]
    vals = np.full(1326, -1, np.int64)
    live = ~np.isin(COMBO, board).any(axis=1)
    vals[live] = evaluate_board_plus(board, COMBO[live])
    return vals


def weighted_showdown(values, weights, board):
    """values: int64[1326] (e.g. river_values); weights: float64[1326] opponent range.
    Returns (beat, tie), float64[1326]: weight of opponent hands that each hand beats / ties.
    Hands that hit the board get 0, and their weights are ignored."""
    board = [int(c) for c in board]
    values = np.asarray(values, dtype=np.int64)
    weights = np.asarray(weights, dtype=np.float64)
    live = np.nonzero(~np.isin(COMBO, board).any(axis=1))[0]
    v = values[live]; w = weights[live]
    order = np.argsort(v, kind="stable")
    sv = v[order]
    new = np.ones(len(sv), bool); new[1:] = sv[1:] != sv[:-1]
    dense = np.cumsum(new) - 1
    rid = np.empty_like(dense); rid[order] = dense
    K = int(dense[-1]) + 1
    wk = np.bincount(rid, weights=w, minlength=K)
    below = np.cumsum(wk) - wk                              # weight strictly below each value
    a, b = COMBO[live, 0], COMBO[live, 1]
    pc = np.bincount(np.concatenate([a * K + rid, b * K + rid]),
                     weights=np.concatenate([w, w]), minlength=52 * K).reshape(52, K)
    pbelow = np.cumsum(pc, axis=1) - pc                     # per card: weight strictly below
    beat_l = below[rid] - pbelow[a, rid] - pbelow[b, rid]
    tie_l = wk[rid] - pc[a, rid] - pc[b, rid] + w           # h itself was removed twice
    beat = np.zeros(1326); tie = np.zeros(1326)
    beat[live] = np.maximum(beat_l, 0.0)                    # clip float round-off below zero
    tie[live] = np.maximum(tie_l, 0.0)
    return beat, tie
