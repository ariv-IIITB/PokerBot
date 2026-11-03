"""RA spike: the river solver (vector CFR+) against brute force and lab/cfr/exact.py."""
import time

import numpy as np
import pytest

from bot.game.rules_spec import holdem_rules
from bot.strategy.river_solver import (FOLD, INF, RAISE, DenseKernel, RiverSpot, SortedKernel, Tree,
                                       TreeCfg, _Dir, bucket_kernel, bucket_ranges, combos_excluding,
                                       hand_ranks, make_solver, solve_river)
from lab.cfr.exact import Tree as ExactTree
from lab.cfr.exact import exploitability

EV = holdem_rules().evaluator


def _board_and_pool(seed: int, pool_size: int):
    rng = np.random.default_rng(seed)
    deck = rng.permutation(52)
    board = deck[:5]
    return board, deck[5:5 + pool_size]


def _combos(cards) -> np.ndarray:
    i, j = np.triu_indices(len(cards), 1)
    return np.stack([np.asarray(cards)[i], np.asarray(cards)[j]], axis=1).astype(np.int64)


class ToyRiver:
    """The solver's own betting tree played as a game for lab/cfr/exact.py: the payoffs of a
    terminal are recomputed here pair by pair (no prefix sums, no card-removal tricks)."""

    def __init__(self, tree, hero, opp, w0, w1, r0, r1) -> None:
        self.t, self.hero, self.opp, self.r0, self.r1 = tree, hero, opp, r0, r1
        pairs = []
        for i, h in enumerate(hero):
            for j, o in enumerate(opp):
                if not set(h.tolist()) & set(o.tolist()):
                    pairs.append((i, j, w0[i] * w1[j]))
        z = sum(p[2] for p in pairs)
        self.pairs = [(i, j, w / z) for i, j, w in pairs]

    def chance_outcomes(self):
        return [((i, j, 0), w) for i, j, w in self.pairs]

    def is_terminal(self, s):
        return self.t.kind[s[2]] != 0

    def utility(self, s, p):
        i, j, n = s
        c0, c1 = self.t.term[n]
        if self.t.kind[n] == 1:
            u0 = c0
        else:
            u0 = c0 * float(np.sign(self.r0[i] - self.r1[j]))
        return u0 if p == 0 else -u0

    def to_act(self, s):
        return self.t.depth[s[2]] % 2

    def actions(self, s):
        return list(range(len(self.t.children[s[2]])))

    def play(self, s, a):
        return (s[0], s[1], self.t.children[s[2]][a])

    def infoset(self, s, p):
        return (p, s[0] if p == 0 else s[1], s[2])


def _toy(seed: int, spot: RiverSpot, pool: int = 7, cfg: TreeCfg = TreeCfg()):
    board, cards = _board_and_pool(seed, pool)
    hero = _combos(cards[:pool])
    opp = _combos(cards[:pool])
    rng = np.random.default_rng(seed + 1)
    w0 = rng.random(len(hero)) + 0.2
    w1 = rng.random(len(opp)) + 0.2
    r0 = hand_ranks(EV, hero, board)
    r1 = hand_ranks(EV, opp, board)
    return board, hero, opp, w0, w1, r0, r1


SPOTS = [
    RiverSpot(pot=20, hero_stack=90, opp_stack=90),                                   # we act first
    RiverSpot(pot=20, hero_stack=90, opp_stack=90, checked=True),                     # they checked
    RiverSpot(pot=30, opp_bet=10, hero_stack=85, opp_stack=75, last_raise=10, aggr_so_far=1),
    RiverSpot(pot=60, hero_bet=10, opp_bet=30, hero_stack=40, opp_stack=20, last_raise=20, aggr_so_far=2),
]


@pytest.mark.parametrize("kernel", ["sorted", "dense"])
@pytest.mark.parametrize("spot", SPOTS)
def test_toy_exploitability_under_two_percent_of_pot(spot, kernel) -> None:
    board, hero, opp, w0, w1, r0, r1 = _toy(3, spot)
    s = make_solver(spot, hero, w0, r0, opp, w1, r1, kernel=kernel, dtype=np.float64, track_all=True)
    s.run(1e18, max_iters=400)
    game = ToyRiver(s.tree, hero, opp, w0, w1, r0, r1)
    tree = ExactTree(game)
    avg = s.average()

    def policy(key, n):
        p, hand, node = key
        return avg[s.row_of[node], :n, hand]

    exact = exploitability(tree, policy)
    assert exact <= 0.02, exact                                  # 2 % of the pot (pot units)
    assert abs(exact - s.exploitability()) < 1e-6                # the vector best response agrees


def test_terminal_values_match_brute_force() -> None:
    board, hero, opp, w0, w1, r0, r1 = _toy(5, SPOTS[0], pool=9)
    rng = np.random.default_rng(0)
    z = rng.random((4, len(opp)))
    ok = np.array([[not set(h.tolist()) & set(o.tolist()) for o in opp] for h in hero], float)
    sign = np.sign(r0[:, None] - r1[None, :]) * ok
    d = _Dir(r0, hero, r1, opp, np.float64)
    assert np.allclose(d.show(z), z @ sign.T)
    assert np.allclose(d.fold(z), z @ ok.T)
    dk = DenseKernel.exact(hero, r0, opp, r1, np.float64)
    sk = SortedKernel(hero, r0, opp, r1, np.float64)
    zo = rng.random((4, len(hero)))
    for k in (dk, sk):
        assert np.allclose(k.show0(z), z @ sign.T) and np.allclose(k.fold0(z), z @ ok.T)
        assert np.allclose(k.show1(zo), -(zo @ sign)) and np.allclose(k.fold1(zo), zo @ ok)


def test_bucket_kernel_is_expected_sign_between_buckets() -> None:
    rng = np.random.default_rng(4)
    r0 = rng.integers(0, 12, 60)
    r1 = rng.integers(0, 12, 50)
    w0 = rng.random(60) + 0.1
    w1 = rng.random(50) + 0.1
    b0, bw0 = bucket_ranges(r0, w0, 6)
    b1, bw1 = bucket_ranges(r1, w1, 5)
    assert abs(bw0.sum() - w0.sum()) < 1e-9 and b0.max() < 6 and b1.max() < 5
    k = bucket_kernel(r0, w0, b0, r1, w1, b1, np.float64)
    for i in range(b0.max() + 1):
        for j in range(b1.max() + 1):
            mi, mj = b0 == i, b1 == j
            ref = (w0[mi, None] * w1[None, mj] * np.sign(r0[mi, None] - r1[None, mj])).sum() \
                / (w0[mi].sum() * w1[mj].sum())
            assert abs(k.M[i, j] - ref) < 1e-12


def test_card_removal_in_ranges() -> None:
    board, cards = _board_and_pool(1, 2)
    dead = list(board) + list(cards)
    combos = combos_excluding(dead)
    assert len(combos) == 45 * 44 // 2
    assert not set(combos.ravel().tolist()) & set(dead)
    assert (combos[:, 0] < combos[:, 1]).all()


def test_root_strategy_sums_to_one_and_deadline_respected() -> None:
    board, cards = _board_and_pool(2, 2)
    combos = combos_excluding(list(board) + list(cards))
    ranks = hand_ranks(EV, combos, board)
    w = np.ones(len(combos))
    spot = SPOTS[2]
    t0 = time.perf_counter()
    res = solve_river(spot, combos, w, ranks, combos, w, ranks, hero_index=7,
                      deadline=t0 + 0.15, keep_solver=True)
    elapsed = time.perf_counter() - t0
    assert res is not None and res.iterations >= 1
    assert abs(res.probs.sum() - 1.0) < 1e-9 and (res.probs >= 0).all()
    assert len(res.probs) == len(res.labels) == len(res.solver.tree.root_labels)
    assert elapsed < 0.15 + 0.05                                  # at most one iteration over


def test_deadline_already_passed_returns_none() -> None:
    board, cards = _board_and_pool(2, 2)
    combos = combos_excluding(list(board) + list(cards))
    ranks = hand_ranks(EV, combos, board)
    w = np.ones(len(combos))
    assert solve_river(SPOTS[0], combos, w, ranks, combos, w, ranks, 0,
                       deadline=time.perf_counter() - 1.0, min_iters=0) is None


def test_tree_amounts_and_caps() -> None:
    t = Tree(RiverSpot(pot=20, hero_stack=90, opp_stack=50))
    assert t.cap == 50                                            # the shorter stack caps all-in
    assert [l for l in t.root_labels if l[0] == RAISE][-1][1] == 50
    # facing a bet bigger than our stack: refunded down to what we can call
    t = Tree(RiverSpot(pot=120, hero_bet=0, opp_bet=100, hero_stack=40, opp_stack=0))
    assert t.root_labels[0][0] == FOLD and t.cap == 40
    assert [l[0] for l in t.root_labels] == [FOLD, "C"]           # nothing left to raise with
    # raises are capped at max_aggr
    t = Tree(RiverSpot(pot=20, hero_stack=90, opp_stack=90), TreeCfg(max_aggr=1))
    assert max(t.depth) == 3                                      # check, bet, then only fold/call
    assert all(l[0] != RAISE for n in range(t.n) if t.depth[n] >= 2 for l in t.legal_labels[n])
    # zero-sum terminals: hero's and opp's coefficients are opposite on folds
    for k, (c0, c1) in zip(t.kind, t.term):
        if k == 1:
            assert abs(c0 + c1) < 1e-12 and c0 != 0


def test_fold_everything_pot_odds() -> None:
    """Facing a pot-sized bet with the nuts vs air: calling beats folding for the nuts."""
    board = np.array([0, 5, 10, 15, 20])
    cards = np.array([25, 30, 35, 40, 45, 3])
    hero = _combos(cards)
    r = hand_ranks(EV, hero, board)
    spot = RiverSpot(pot=20, opp_bet=10, hero_stack=90, opp_stack=90, last_raise=10, aggr_so_far=1)
    res = solve_river(spot, hero, np.ones(len(hero)), r, hero, np.ones(len(hero)), r,
                      int(np.argmax(r)), deadline=time.perf_counter() + 0.3)
    fold_p = res.probs[[l[0] == FOLD for l in res.labels]].sum()
    assert fold_p < 0.05                                          # the best hand never folds


def _spot_inputs(seed: int = 2):
    board, cards = _board_and_pool(seed, 2)
    combos = combos_excluding(list(board) + list(cards))
    return combos, hand_ranks(EV, combos, board), np.ones(len(combos))


@pytest.mark.parametrize("buckets,kernel", [(0, "sorted"), (0, "dense"), (24, "auto")])
def test_float32_default_and_buckets_respect_deadline(buckets, kernel) -> None:
    combos, ranks, w = _spot_inputs()
    t0 = time.perf_counter()
    res = solve_river(SPOTS[2], combos, w, ranks, combos, w, ranks, hero_index=11,
                      deadline=t0 + 0.3, buckets=buckets, kernel=kernel)
    elapsed = time.perf_counter() - t0
    assert res is not None and res.iterations >= 1
    assert abs(res.probs.sum() - 1.0) < 1e-9 and (res.probs >= 0).all()
    assert elapsed < 0.3 + 0.1                                    # at most one pass over


def test_bucketed_best_hand_never_folds_and_air_rarely_calls() -> None:
    board = np.array([0, 5, 10, 15, 20])
    cards = np.array([25, 30, 35, 40, 45, 3])
    hero = _combos(cards)
    r = hand_ranks(EV, hero, board)
    spot = RiverSpot(pot=20, opp_bet=10, hero_stack=90, opp_stack=90, last_raise=10, aggr_so_far=1)
    w = np.ones(len(hero))
    best = solve_river(spot, hero, w, r, hero, w, r, int(np.argmax(r)), time.perf_counter() + 0.2,
                       buckets=6, max_iters=600)
    worst = solve_river(spot, hero, w, r, hero, w, r, int(np.argmin(r)), time.perf_counter() + 0.2,
                        buckets=6, max_iters=600)
    fold = [l[0] == FOLD for l in best.labels]
    assert best.probs[fold].sum() < 0.05
    assert worst.probs[fold].sum() > best.probs[fold].sum()


def test_bucketed_exploitability_small_in_its_own_game() -> None:
    combos, ranks, w = _spot_inputs(7)
    s = solve_river(SPOTS[0], combos, w, ranks, combos, w, ranks, 5, time.perf_counter() + 5.0,
                    buckets=32, max_iters=300, keep_solver=True, track_all=True, dtype=np.float64).solver
    assert s.exploitability() < 0.02
