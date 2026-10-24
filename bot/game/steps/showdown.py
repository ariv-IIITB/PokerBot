"""Final settlement step (runs even after a fold)."""
from __future__ import annotations

from bot.game.payoffs import settle
from bot.game.steps.base import Step


class ShowdownStep(Step):
    """Pay the pot: to the non-folder, or to the best hand at showdown (split on ties)."""
    type_name = "showdown"
    skip_on_fold = False

    def apply(self, st, rng) -> None:
        settle(st, st.rules.evaluator.evaluate)

    def describe(self) -> str:
        return "showdown: best hand wins the pot (fold: the other player wins)"
