"""Worked plugin example (docs/WRITING_A_PLUGIN.md): redraw one board card.

Rule: each player in turn (BB first by default) may pay `cost` chips into the pot to
replace one card of the shared board with the next card from the deck. The old card goes
to the muck face up (both see it), the new card is public. Choices: "none" or "b<i>"
(board card i). Unaffordable -> only "none".
"""
from __future__ import annotations

from bot.game.state import ALL
from bot.game.steps.cards import CardStep


class RedrawBoard(CardStep):
    type_name = "redraw_board"
    free_choices = ("none",)

    def __init__(self, cost: int = 0, order: str = "BB_first") -> None:
        super().__init__(order=order, cost=cost, visibility="public")

    @classmethod
    def from_spec(cls, s, ctx):
        return cls(s["cost"], s["order"])

    def options(self, st, p: int) -> tuple[str, ...]:
        if not st.board or not st.deck:
            return ()
        return ("none",) + tuple(f"b{i}" for i in range(len(st.board)))

    def perform(self, st, p: int, choice: str) -> None:
        if choice == "none":
            return
        i = int(choice[1:])
        old = st.board[i]
        st.muck.append(old)
        new_board = list(st.board)
        new_board[i] = st.deal(1)[0]
        st.board = new_board
        st.emit("reveal", p, visible=ALL, cards=(old,), what="redrawn")
        self.show_board(st)

    def describe(self) -> str:
        cost = f" for {self.cost} chips" if self.cost else ""
        return f"each player ({self.order.replace('_', ' ')}) may redraw one board card{cost}"
