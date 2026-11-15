"""Street features and card buckets (BUILDMAP §4.5, §4.6, §5.1, Appendix A).

Pipeline per street: street_rows (evaluate once; callers cache it per hand and street)
-> own_features (our pairs) or all_features (all 1326 pairs, for range tracking)
-> buckets via the fitted thresholds.

Dead cards (other hole cards, discards) are deliberately ignored here (§4.5).
"""
import hashlib
import json

import numpy as np

from . import abstraction as AB
from .cards import COMBO, idx2
from .evaluator import evaluate_board_plus

N_NEXT_FLOP = 47            # turn cards for a pair on the flop
N_NEXT_TURN = 46            # river cards for a pair on the turn
N_CLASS2 = 80
N_B3 = 400
N_BT = 200
N_BR = 100

# ---------------------------------------------------------------- Appendix A: all-hands features

def street_rows(board, lookahead):
    """Evaluate every (next card x, pair h) row once per street; reuse for own and all-pairs counts.
    Groups g are next cards x (turn card on the flop, river card on the turn); the river has one group."""
    board = [int(c) for c in board]
    live = np.array([c for c in range(52) if c not in board], dtype=np.int64)
    nexts = live if lookahead else np.array([-1], dtype=np.int64)
    G = len(nexts)
    hidx = np.nonzero(~np.isin(COMBO, board).any(axis=1))[0]
    gi = np.repeat(np.arange(G), len(hidx)); hi = np.tile(hidx, G)
    x = nexts[gi]
    keep = (COMBO[hi, 0] != x) & (COMBO[hi, 1] != x)
    gi, hi, x = gi[keep], hi[keep], x[keep]
    extra = np.column_stack([COMBO[hi], x]) if lookahead else COMBO[hi]
    return dict(G=G, gi=gi, hi=hi, val=evaluate_board_plus(board, extra))


def own_features(rows, pairs):
    """[(S1, S2)] for each (a, b) in pairs (a < b). Cheap: no sorting."""
    G, gi, hi, val = rows["G"], rows["gi"], rows["hi"], rows["val"]
    ca, cb = COMBO[hi, 0], COMBO[hi, 1]
    out = []
    for a, b in pairs:
        h = b * (b - 1) // 2 + a
        mine = hi == h
        gv = np.full(G, -1, np.int64); gv[gi[mine]] = val[mine]       # -1: group's card hits our pair
        mv = gv[gi]
        ok = (mv >= 0) & (ca != a) & (ca != b) & (cb != a) & (cb != b)
        E = (2 * np.bincount(gi[ok & (val < mv)], minlength=G)
             + np.bincount(gi[ok & (val == mv)], minlength=G))[gv >= 0].astype(np.int64)
        out.append((int(E.sum()), int((E * E).sum())))
    return out


def all_features(rows):
    """S1, S2 for all 1326 pairs (zero where the pair hits the board). One lexsort + bincounts."""
    G, gi, hi, val = rows["G"], rows["gi"], rows["hi"], rows["val"]
    order = np.lexsort((val, gi))                       # by group, then value
    sv, sg = val[order], gi[order]
    new = np.ones(len(order), bool); new[1:] = (sv[1:] != sv[:-1]) | (sg[1:] != sg[:-1])
    dense = np.cumsum(new) - 1                          # global dense id of (group, value)
    rid = np.empty_like(dense); rid[order] = dense
    K = int(dense[-1]) + 1
    first = np.ones(len(order), bool); first[1:] = sg[1:] != sg[:-1]
    gfirst = np.zeros(G, np.int64); gfirst[sg[first]] = dense[first]
    cnt = np.bincount(rid, minlength=K); cum = np.cumsum(cnt) - cnt
    g0 = gfirst[gi]
    less_tot = cum[rid] - cum[g0]; eq_tot = cnt[rid]
    a, b = COMBO[hi, 0], COMBO[hi, 1]
    pc = np.bincount(np.concatenate([a * K + rid, b * K + rid]), minlength=52 * K).reshape(52, K)
    pcum = np.cumsum(pc, axis=1) - pc                   # per card: hands strictly below
    W = less_tot - (pcum[a, rid] - pcum[a, g0]) - (pcum[b, rid] - pcum[b, g0])
    T = eq_tot - pc[a, rid] - pc[b, rid] + 1
    E = 2 * W + T
    S1 = np.bincount(hi, weights=E, minlength=1326).astype(np.int64)
    S2 = np.bincount(hi, weights=(E * E).astype(np.float64), minlength=1326).astype(np.int64)
    return S1, S2


def street_features(board, lookahead):
    return all_features(street_rows(board, lookahead))


# ---------------------------------------------------------------- thresholds (§5.1.8)

class Thresholds:
    """Fitted bucket edges. Built from the exact bytes of a thresholds.json so the sha matches.
    (The bot gets these bytes from its embedded blob; it never reads files.)
    The file names its abstraction ("abstraction" key; a1's file, data/thresholds.json, has none), which
    sets the shapes; `abstraction`, if given, must agree."""

    SHAPES = AB.A1.threshold_shapes()           # a1's (the frozen file)

    def __init__(self, d, sha, abstraction=None):
        A = AB.get(d.get("abstraction"))
        if abstraction is not None and AB.get(getattr(abstraction, "name", abstraction)) != A:
            raise ValueError(f"thresholds are abstraction {A.name}, expected {getattr(abstraction, 'name', abstraction)}")
        for k, shape in A.threshold_shapes().items():
            arr = np.asarray(d[k], dtype=np.int64)
            if arr.shape != shape:
                raise ValueError(f"thresholds {k}: shape {arr.shape}, expected {shape}")
            if (np.diff(arr, axis=-1) < 0).any():
                raise ValueError(f"thresholds {k}: edges not sorted")
            setattr(self, k, arr)
        self.A = A
        self.sha = sha

    @classmethod
    def from_json_bytes(cls, raw, expect_sha=None, abstraction=None):
        sha = hashlib.sha256(raw).hexdigest()
        if expect_sha is not None and sha != expect_sha:
            raise ValueError(f"thresholds sha mismatch: {sha} != {expect_sha}")
        return cls(json.loads(raw), sha, abstraction)


# ---------------------------------------------------------------- bins and buckets (§4.6, §5.1)

def bin_index(x, edges):
    """Number of edges <= x (= searchsorted side='right' = std::upper_bound). Scalar or array."""
    r = np.searchsorted(edges, x, side="right")
    return int(r) if np.ndim(r) == 0 else r.astype(np.int64)


def flop_v(S1, S2):
    """V = 47*S2 - S1^2 (int64 / Python int)."""
    return N_NEXT_FLOP * S2 - S1 * S1


def turn_v(S1, S2):
    """V = 46*S2 - S1^2."""
    return N_NEXT_TURN * S2 - S1 * S1


def _two_level(S1, V, s1_edges, v_edges):
    """s1bin * n_v + vbin, where vbin uses the V edges of that s1bin (n_v = V edges per bin + 1;
    a1: 5). Scalar or array."""
    s1bin = np.searchsorted(s1_edges, S1, side="right")
    V = np.asarray(V, dtype=np.int64)
    vbin = (v_edges[s1bin] <= V[..., None]).sum(axis=-1)    # edges sorted -> = upper_bound
    out = s1bin * (v_edges.shape[1] + 1) + vbin
    return int(out) if np.ndim(out) == 0 else out.astype(np.int64)


def class2(S1, V, th):
    """Flop pair class in [0, th.A.n_class2) (§5.1.2; a1: 80)."""
    return _two_level(S1, V, th.flop_s1, th.flop_v)


def turn_bucket(S1, V, th):
    """Turn bucket bt in [0, th.A.n_bt) (§5.1.6; a1: 200)."""
    return _two_level(S1, V, th.turn_s1, th.turn_v)


def river_bucket(E, th):
    """River bucket br in [0, th.A.n_br) (§5.1.7; 100)."""
    return bin_index(E, th.river)


def hand_pairs(hand3):
    """The three pairs (a < b) of a 3-card hand, in idx2-ascending order."""
    a, b, c = sorted(int(x) for x in hand3)
    return [(a, b), (a, c), (b, c)]             # idx2 ascending for a < b < c


def keep_order(hand3, s1):
    """Pairs in keep-slot order: S1 descending, then idx2 ascending (§5.1.3).
    s1: S1 of each pair, aligned with hand_pairs(hand3)."""
    pairs = hand_pairs(hand3)
    order = sorted(range(3), key=lambda i: (-s1[i], idx2(*pairs[i])))
    return [pairs[i] for i in order]


def bucket3(hand3, s1, s2, th):
    """(b3, pairs in keep-slot order) for a 3-card hand on the flop (§5.1.3).
    s1, s2: features of each pair, aligned with hand_pairs(hand3)."""
    pairs = hand_pairs(hand3)
    order = sorted(range(3), key=lambda i: (-s1[i], idx2(*pairs[i])))
    i0, i1 = order[0], order[1]
    c2 = class2(s1[i0], flop_v(s1[i0], s2[i0]), th)
    gapbin = bin_index(s1[i0] - s1[i1], th.gap)
    return c2 * (len(th.gap) + 1) + gapbin, [pairs[i] for i in order]


def flop_bucket3(rows, hand3, th):
    """Convenience for the bot: own_features on the cached flop rows -> (b3, slots)."""
    pairs = hand_pairs(hand3)
    f = own_features(rows, pairs)
    return bucket3(hand3, [x[0] for x in f], [x[1] for x in f], th)


def dcls(d, flop):
    """Discard class (§5.1.5): 0 pairs the flop, 1 overcard, 2 flush card, 3 other."""
    r, s = d >> 2, d & 3
    franks = [c >> 2 for c in flop]
    if r in franks:
        return 0
    if r > max(franks):
        return 1
    if sum(1 for c in flop if (c & 3) == s) >= 2:
        return 2
    return 3


# ---------------------------------------------------------------- vectorised variants (range tracking)
# Inputs are the 1326-long S1/S2 arrays from all_features. Entries for pairs that hit the board
# are meaningless; callers mask them out.

def class2_all(S1, S2, th):
    return class2(S1, flop_v(S1, S2), th)


def turn_bucket_all(S1, S2, th):
    return turn_bucket(S1, turn_v(S1, S2), th)


def river_bucket_all(E, th):
    return river_bucket(E, th)


_S1_KEY = 1 << 20           # > any S1 (max 47 * 2070 = 97,290)


def bucket3_all(hands3, S1, c2_all, th):
    """Vectorised bucket3 for many 3-card hands (N, 3) on one flop.
    Returns b3 (N,) and the idx2 of each hand's pairs in keep-slot order (N, 3)."""
    h = np.sort(np.asarray(hands3, dtype=np.int64), axis=1)
    a, b, c = h[:, 0], h[:, 1], h[:, 2]
    p = np.stack([b * (b - 1) // 2 + a, c * (c - 1) // 2 + a, c * (c - 1) // 2 + b], axis=1)
    s = S1[p]
    key = (_S1_KEY - s) * 2048 + p              # S1 descending, then idx2 ascending
    order = np.argsort(key, axis=1)
    slots = np.take_along_axis(p, order, axis=1)
    s_sorted = np.take_along_axis(s, order, axis=1)
    gapbin = np.searchsorted(th.gap, s_sorted[:, 0] - s_sorted[:, 1], side="right")
    b3 = c2_all[slots[:, 0]] * (len(th.gap) + 1) + gapbin
    return b3.astype(np.int64), slots
