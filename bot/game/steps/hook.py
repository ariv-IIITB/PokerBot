"""Adapter that runs a legacy `variant.rules.SpecialStep` hook as a program step.

The hook's choices(state, role) / apply(state, role, choice) receive the GameState, which
has the same attributes the old engine's hand object had (hole, board, deck, ...).
"""
from __future__ import annotations

from typing import Optional

from bot.actions import Action, LegalActions, SpecialOption
from bot.game.state import ALL
from bot.game.steps.base import Step

ROLE = {"SB": 0, "BB": 1}


class _Queue:
    __slots__ = ("order", "current", "options")

    def __init__(self, order: list[int]) -> None:
        self.order, self.current, self.options = order, None, ()

    def copy(self) -> "_Queue":
        q = _Queue(list(self.order))
        q.current, q.options = self.current, self.options
        return q


class HookStep(Step):
    """A special decision (e.g. a discard) defined by a SpecialStep hook."""
    type_name = "hook"
    decision = True

    def __init__(self, hook) -> None:
        super().__init__(name=hook.name, order=hook.order)
        self.hook = hook

    def begin(self, st) -> None:
        st.step_state = _Queue([ROLE[r] for r in self.hook.order])

    def next_actor(self, st) -> Optional[int]:
        q: _Queue = st.step_state
        if q.current is not None:
            return q.current
        while q.order:
            p = q.order.pop(0)
            options = tuple(self.hook.choices(st, p))
            if options:
                q.current, q.options = p, options
                return p
        return None

    def legal(self, st, p: int) -> LegalActions:
        return LegalActions(special=SpecialOption(self.hook.name, st.step_state.options))

    def apply_choice(self, st, p: int, a: Action) -> None:
        board_before = list(st.board)
        self.hook.apply(st, p, a.choice)
        st.emit("special", p, visible=ALL, action=a)
        st.emit("hole", p, visible=p, cards=tuple(st.hole[p]))
        if st.board != board_before:
            st.emit("board", visible=ALL, street=st.street, cards=tuple(st.board))
        st.step_state.current = None

    def describe(self) -> str:
        return f"special step '{self.hook.name}' ({' then '.join(self.hook.order)})"
