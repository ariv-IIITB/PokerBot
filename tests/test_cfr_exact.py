"""Phase 23: Leduc Hold'em, exact best response / exploitability, reference CFR+."""
import numpy as np
import pytest

from lab.cfr import mccfr
from lab.cfr.exact import Tree, best_response_value, expected_value, exploitability, solve_cfr_plus
from lab.cfr.kuhn import Kuhn
from lab.cfr.leduc import Leduc

UNIFORM = lambda key, n: np.full(n, 1.0 / n)  # noqa: E731


def test_leduc_rules_and_payoffs() -> None:
    g = Leduc()
    assert g.contributions("rrc/crrc") == ([13, 13], -1)     # 1 + 4 (round 1) + 8 (round 2)
    assert g.contributions("rf") == ([3, 1], 1)
    s = (0, 2, 4, "cc/cc")                                     # J vs Q, board K: Q wins 1
    assert g.utility(s, 0) == -1 and g.utility(s, 1) == 1
    s = (0, 2, 1, "cc/rc")                                     # J pairs the board (J)
    assert g.utility(s, 0) == 5
    assert g.utility((0, 1, 4, "cc/cc"), 0) == 0               # J vs J: split
    assert g.actions((0, 1, -1, "rr")) == ["f", "c"]           # raise cap 2
    assert g.to_act((0, 1, -1, "cc")) is None                  # board to deal
    assert g.to_act((0, 1, 3, "cc/c")) == 1


def test_leduc_tree_size() -> None:
    t = Tree(Leduc())
    assert len(t.infosets(0)) == len(t.infosets(1)) == 144    # ranks only (lossless)
    assert abs(sum(w for _, w in t.roots) - 1.0) < 1e-12


def test_exact_matches_kuhn_enumeration() -> None:
    g = Kuhn()
    t = Tree(g)
    m = mccfr.MCCFR(g, seed=0)
    m.iterate(2000)
    assert abs(exploitability(t, m.average_strategy) - mccfr.exploitability(g, m.average_strategy)) < 1e-12
    assert abs(exploitability(t, UNIFORM) - mccfr.exploitability(g, UNIFORM)) < 1e-12


def test_best_response_dominates_policy_value() -> None:
    t = Tree(Leduc())
    for p in (0, 1):
        assert best_response_value(t, UNIFORM, p) >= expected_value(t, UNIFORM, p) - 1e-12
    assert abs(exploitability(t, UNIFORM) - 2.3736111) < 1e-6   # known value for uniform play


def test_reference_cfr_plus_kuhn() -> None:
    t = Tree(Kuhn())
    pol = solve_cfr_plus(t, 300)
    assert exploitability(t, pol) < 0.003
    assert abs(expected_value(t, pol, 0) + 1 / 18) < 0.003


@pytest.mark.slow
def test_reference_cfr_plus_leduc_value() -> None:
    t = Tree(Leduc())
    pol = solve_cfr_plus(t, 150)
    assert exploitability(t, pol) < 0.015
    assert abs(expected_value(t, pol, 0) - (-0.0856)) < 0.004  # Leduc's game value


def test_mccfr_leduc_improves() -> None:
    g = Leduc()
    t = Tree(g)
    m = mccfr.MCCFR(g, seed=1)
    m.iterate(200)
    e1 = exploitability(t, m.average_strategy)
    m.iterate(2000)
    e2 = exploitability(t, m.average_strategy)
    assert e2 < e1 < exploitability(t, UNIFORM)
