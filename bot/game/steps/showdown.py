"""Final settlement step (runs even after a fold)."""
from __future__ import annotations

from bot.game.payoffs import settle
from bot.game.steps.base import Step


class ShowdownStep(Step):
    """Pay the pot: to the non-folder, or by the scorer at showdown (split on ties).
    runs > 1: after an all-in, the rest of the board is dealt `runs` times and each run
    decides an equal share of the pot. Payoff modifiers (rake, multiplier) come from the
    rules; bounties and side markets from earlier steps."""
    type_name = "showdown"
    skip_on_fold = False

    def __init__(self, runs: int = 1) -> None:
        super().__init__(runs=runs)
        self.runs = runs

    @classmethod
    def from_spec(cls, s, ctx):
        return cls(s.get("runs", 1))

    def apply(self, st, rng) -> None:
        settle(st, st.rules.evaluator, self.runs, getattr(st.rules, "payoffs", ()))

    def describe(self) -> str:
        runs = f"; after an all-in the board is run {self.runs} times" if self.runs > 1 else ""
        return f"showdown: best hand wins the pot (fold: the other player wins){runs}"
