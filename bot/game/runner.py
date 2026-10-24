"""Drives a GameState through its hand program.

    actor = advance(st, rng)        # run automatic steps; returns who must decide (or None)
    legal = legal_actions(st, actor)
    act(st, actor, action)          # apply a legal choice, then call advance again

`play_out(st, policy, rng)` runs a whole hand with a policy function (used by simulations
and tests).
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from bot.actions import Action, LegalActions


class LazyRng:
    """A numpy Generator created on first use (most hands never need randomness, and
    creating a seeded Generator costs more than a whole simple hand)."""

    __slots__ = ("_seed", "_rng")

    def __init__(self, seed) -> None:
        self._seed, self._rng = seed, None

    def __getattr__(self, name):
        if self._rng is None:
            self._rng = np.random.default_rng(self._seed)
        return getattr(self._rng, name)


def current_step(st):
    return st.rules.program[st.pc]


def advance(st, rng=None) -> Optional[int]:
    """Run until a player must decide (returns that player) or the hand ends (None)."""
    prog = st.rules.program
    while st.pc < len(prog):
        step = prog[st.pc]
        if not st.entered:
            if st.folded is not None and step.skip_on_fold:
                st.pc += 1
                continue
            st.entered = True
            step.begin(st)
            if not step.decision:
                step.apply(st, rng)
                _finish(st, step)
                continue
        actor = step.next_actor(st)
        if actor is not None:
            return actor
        _finish(st, step)
    st.done = True
    return None


def _finish(st, step) -> None:
    step.end(st)
    st.pc += 1
    st.entered = False
    st.step_state = None


def legal_actions(st, p: int) -> LegalActions:
    return current_step(st).legal(st, p)


def act(st, p: int, action: Action) -> None:
    current_step(st).apply_choice(st, p, action)


def play_out(st, policy: Callable, rng=None) -> list[int]:
    """Play to the end with policy(st, player, legal) -> Action. Returns chip deltas."""
    while True:
        p = advance(st, rng)
        if p is None:
            return st.deltas  # type: ignore[return-value]
        act(st, p, policy(st, p, legal_actions(st, p)))
