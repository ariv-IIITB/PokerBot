"""C0: the v1 abstract betting tree (lab/cfr/fast/tree.py, docs/cfr/ABSTRACTION_V1.md).

The tree is the reference the fast game core (C1) and the runtime key builder (C5) must equal,
so its chips are checked against the real rules engine (bot/game) along random lines.
"""
import numpy as np
import pytest

from bot.actions import Action
from bot.game.rules_spec import to_rules
from bot.game.runner import act, advance, legal_actions
from bot.game.state import GameState
from lab.cfr.fast import tree
from lab.harness import load_variant


@pytest.fixture(scope="module")
def par() -> tree.Params:
    return tree.Params.from_variant("discard_holdem")


def menu(n, par) -> str:
    return " ".join(lab + ("" if amt is None else f"{amt}") for lab, _k, amt in tree.actions(n, par))


def test_params_come_from_the_variant_spec(par) -> None:
    assert (par.stack, par.sb, par.bb, par.max_raises, par.blind_counts_as_raise) == (200, 1, 2, 4, True)
    assert par.sized_raise_cap == 3


def test_the_worked_example_of_the_contract(par) -> None:
    """The line in docs/cfr/ABSTRACTION_V1.md section 6, decision by decision."""
    steps = tree.walk_line("R R C | C H C | C P R A C", par)
    got = [(n.street, n.actor, n.pot, n.history, menu(n, par), label) for n, _a, label in steps]
    assert got == [
        (0, 0, 3, "", "F C R5 A200", "R"),
        (0, 1, 7, "R", "F C R15 A200", "R"),
        (0, 0, 20, "RR", "F C A200", "C"),            # 3 raises (BB, R, R): only all-in left
        (1, 1, 30, "RRC/", "C H15 P30 A185", "C"),
        (1, 0, 30, "RRC/C", "C H15 P30 A185", "H"),
        (1, 1, 45, "RRC/CH", "F C R38 A185", "C"),
        (2, 1, 60, "RRC/CHC/", "C H30 P60 A170", "C"),
        (2, 0, 60, "RRC/CHC/C", "C H30 P60 A170", "P"),
        (2, 1, 120, "RRC/CHC/CP", "F C R150 A170", "R"),
        (2, 0, 270, "RRC/CHC/CPR", "F C A170", "A"),
        (2, 1, 380, "RRC/CHC/CPRA", "F C", "C"),
    ]
    end = tree.child(steps[-1][0], "C", par)
    assert end.done and end.history == "RRC/CHC/CPRAC/" and end.pot == 400


def test_sizes_round_half_to_even_and_merge_into_all_in(par) -> None:
    flop = tree.child(tree.child(tree.root(par), "C", par), "C", par)     # limped pot
    assert flop.pot == 4 and menu(flop, par) == "C H2 P4 A198"
    # 2.5 x 7 = 17.5 rounds to 18 (half to even), 2.5 x 5 = 12.5 rounds to 12
    facing7 = tree.Node(1, (7, 0), (190, 197), 1, 7, 1, frozenset({1}), _start_stack=200)
    facing5 = tree.Node(1, (5, 0), (192, 197), 1, 5, 1, frozenset({1}), _start_stack=200)
    assert menu(facing7, par) == "F C R18 A197" and menu(facing5, par) == "F C R12 A197"
    short = tree.Node(1, (0, 0), (3, 3), 0, 2, 1, frozenset({0, 1}), _start_stack=200)
    assert menu(short, par) == "C A3"           # H and P clamp to all-in: one label, A


def test_from_the_sized_raise_cap_on_only_all_in_is_offered(par) -> None:
    n = tree.root(par)
    for label in ("C", "R", "R"):                          # BB, R, R = 3 raises
        n = tree.child(n, label, par)
    assert n.raises == 3 and [lab for lab, _k, _a in tree.actions(n, par)] == ["F", "C", "A"]


def _settle(st):
    while True:
        p = advance(st)
        if p is None:
            return None
        legal = legal_actions(st, p)
        if legal.can_special:                 # the discard: any legal choice
            act(st, p, Action.special(legal.special.default()))
            continue
        return p


def _engine_action(kind: str, amount):
    return {"F": Action.fold, "K": Action.check, "C": Action.call}[kind]() if kind != "R" \
        else Action.raise_to(amount)


@pytest.mark.parametrize("cap", [4, 3, 2])
def test_tree_chips_equal_the_rules_engine_on_random_lines(par, cap) -> None:
    from dataclasses import replace
    par = replace(par, sized_raise_cap=cap)
    rules = to_rules(load_variant("discard_holdem"))
    rng = np.random.default_rng(11 + cap)
    for _ in range(400):
        deck = [rules.deck[i] for i in rng.permutation(len(rules.deck))]
        st = GameState(rules, deck, [rules.starting_stack] * 2, record=False)
        n = tree.root(par)
        p = _settle(st)
        while p is not None:
            assert not n.done
            assert (n.actor, n.street, n.pot, n.to_call(n.actor)) == (p, st.street, st.pot, st.to_call(p))
            legal = legal_actions(st, p)
            bounds = tree._raise_bounds(n, par)
            assert bounds == ((legal.raise_min, legal.raise_max) if legal.can_raise else None)
            acts = tree.actions(n, par)
            for _lab, kind, amt in acts:
                assert kind != "R" or legal.raise_ok(amt)
            label, kind, amt = acts[int(rng.integers(len(acts)))]
            act(st, p, _engine_action(kind, amt))
            n = tree.child(n, label, par)
            p = _settle(st)
        assert n.done


def test_history_ids_are_dense_per_street(par) -> None:
    ids = tree.history_ids(par)
    assert [len(d) for d in ids] == [12, 132, 1196, 6964]
    for d in ids:
        assert sorted(d.values()) == list(range(len(d)))
    assert ids[0][""] == 0 and "RRC/" in ids[1] and "RRC/CHC/CP" in ids[2]
