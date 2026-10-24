"""Core automatic steps: posting blinds, dealing hole cards, dealing board cards."""
from __future__ import annotations

from bot.game.state import ALL
from bot.game.steps.base import Step


class PostBlinds(Step):
    """Small blind posts `sb`, big blind posts `bb` (all-in if short). The minimum raise
    increment starts at the big blind."""
    type_name = "post_blinds"

    def __init__(self, sb: int, bb: int) -> None:
        super().__init__(sb=sb, bb=bb)
        self.sb, self.bb = sb, bb

    def apply(self, st, rng) -> None:
        paid = (st.pay(0, self.sb), st.pay(1, self.bb))
        st.last_raise = self.bb
        st.emit("blinds", visible=ALL, amounts=paid)

    def describe(self) -> str:
        return f"post blinds {self.sb}/{self.bb}"


class DealHole(Step):
    """Each player gets `n` private hole cards (small blind's first, then big blind's)."""
    type_name = "deal_hole"

    def __init__(self, n: int) -> None:
        super().__init__(n=n)
        self.n = n

    def apply(self, st, rng) -> None:
        for p in range(st.n_players):
            st.hole[p] = st.hole[p] + st.deal(self.n)
        for p in range(st.n_players):
            st.emit("hole", p, visible=p, cards=tuple(st.hole[p]))

    def describe(self) -> str:
        return f"deal {self.n} hole card{'s' * (self.n != 1)} to each player"


class DealBoard(Step):
    """Start a new street: burn `burn` cards (shown to both if burn_revealed), then deal
    `n` public cards to the board (n may be 0: a betting round with no new cards)."""
    type_name = "deal_board"

    def __init__(self, n: int, burn: int = 0, burn_revealed: bool = False) -> None:
        super().__init__(n=n, burn=burn, burn_revealed=burn_revealed)
        self.n, self.burn, self.burn_revealed = n, burn, burn_revealed

    def apply(self, st, rng) -> None:
        st.street += 1
        if self.burn:
            burned = st.deal(self.burn)
            if self.burn_revealed:
                st.emit("burn", visible=ALL, cards=tuple(burned))
        st.board = st.board + st.deal(self.n)
        st.emit("board", visible=ALL, street=st.street, cards=tuple(st.board))

    def describe(self) -> str:
        burn = ""
        if self.burn:
            burn = f"burn {self.burn}{' face up' if self.burn_revealed else ''}, then "
        return f"{burn}deal {self.n} board card{'s' * (self.n != 1)} (new street)"
