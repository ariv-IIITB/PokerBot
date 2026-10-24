"""TEMPLATE for a new step plugin — copy to bot/game/steps/<name>.py and fill in.

Plain-English rule (write this first, it is the docstring the reviewers read):
    "<who> may <do what> <when>; <who sees what>; <what it costs>."

Checklist (docs/WRITING_A_PLUGIN.md has the details):
  [ ] this module: the class below, with a docstring stating the rule
  [ ] bot/game/steps/__init__.py: one line in STEP_TYPES
  [ ] variant/spec.py: the step's parameters and defaults in STEP_PARAMS
      (+ card accounting in _check_cards if it deals or removes cards)
  [ ] variant/catalog/<variant>.json: a preset that uses it
  [ ] lab/random_variant.py: let the random generator use it (fuzz entry)
  [ ] tests/test_<name>.py: legality, effects, conservation, no leaks (audit), protocol
      round-trip of its tokens, default policy, a match with real bots
"""
from __future__ import annotations

from typing import Optional

from bot.actions import Action, LegalActions, SpecialOption
from bot.game.state import ALL
from bot.game.steps.base import Step

# Most player-choice steps should subclass bot.game.steps.cards.CardStep instead: it already
# handles turn order (BB_first / SB_first / simultaneous), costs, and hiding private choices.
# This template shows the bare interface for a step that needs full control.


class TemplateStep(Step):
    type_name = "template"          # the name used in variant specs
    decision = True                 # False for automatic steps (then implement apply())

    def __init__(self, n: int = 1) -> None:
        super().__init__(n=n)       # params are shown by describe() and in logs
        self.n = n

    @classmethod
    def from_spec(cls, s: dict, ctx) -> "TemplateStep":
        """Build from the program entry `s` (defaults from STEP_PARAMS already filled in)."""
        return cls(s["n"])

    # ---- lifecycle -----------------------------------------------------------------
    def begin(self, st) -> None:
        """Set up per-hand progress. st.step_state must support .copy() (simulations copy
        states), so use a small class with a copy() method, or an immutable value."""
        st.step_state = [1, 0]      # e.g. players still to act, in order (BB first)

    def next_actor(self, st) -> Optional[int]:
        """Who decides now; None when the step is finished."""
        return st.step_state[0] if st.step_state else None

    def legal(self, st, p: int) -> LegalActions:
        """Choices as tokens without spaces, commas, pipes or colons ("0", "0+2", "none"),
        or a numeric range: SpecialOption("bid", (), lo, hi)."""
        return LegalActions(special=SpecialOption(self.type_name, ("none", "0")))

    def apply_choice(self, st, p: int, action: Action) -> None:
        """Apply a legal choice. ALL information must go through st.emit():
           st.emit("special", p, visible=ALL, action=action)        # opponent sees choice
           st.emit("hole", p, visible=p, cards=tuple(st.hole[p]))   # p sees new hole cards
           st.emit("board", visible=ALL, street=st.street, cards=tuple(st.board))
        Cards must only move between st.deck / st.hole / st.board / st.boards / st.muck,
        never be created or lost (tests check this)."""
        st.step_state = st.step_state[1:]
        st.emit("special", p, visible=ALL, action=action)

    # ---- optional ------------------------------------------------------------------
    def describe(self) -> str:
        return f"template step (n={self.n})"
