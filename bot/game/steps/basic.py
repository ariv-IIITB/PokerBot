"""Core automatic steps: posting blinds, dealing hole cards, dealing board cards."""
from __future__ import annotations

from bot.game.state import ALL
from bot.game.steps.base import Step


class PostBlinds(Step):
    """Forced bets. Each player first posts the ante (dead money: in the pot, not a bet);
    then the small blind posts `sb` and the big blind `bb` (all-in if short). With a
    straddle, the small blind posts the straddle amount instead of the small blind; the big
    blind then acts first preflop and the minimum raise is to twice the straddle.
    Per-hand amounts come from the state's level (blind schedules), else these defaults."""
    type_name = "post_blinds"

    def __init__(self, sb: int, bb: int, ante: int = 0, straddle: int = 0) -> None:
        super().__init__(sb=sb, bb=bb, ante=ante, straddle=straddle)
        self.sb, self.bb, self.ante, self.straddle = sb, bb, ante, straddle

    def apply(self, st, rng) -> None:
        sb, bb, ante, straddle = st.level if st.level else (self.sb, self.bb, self.ante,
                                                             self.straddle)
        antes = tuple(st.pay_cost(p, ante) for p in range(st.n_players)) if ante else ()
        first = straddle if straddle else sb
        paid = (st.pay(0, first), st.pay(1, bb))
        st.last_raise = straddle if straddle else bb
        st.emit("blinds", visible=ALL, amounts=paid, antes=antes)

    def describe(self) -> str:
        extra = f", ante {self.ante}" if self.ante else ""
        extra += f", SB straddles {self.straddle}" if self.straddle else ""
        return f"post blinds {self.sb}/{self.bb}{extra}"


class DealHole(Step):
    """Each player gets `n` hole cards (small blind's first, then big blind's). The first
    `face_up` of each player's new cards are dealt face up: both players see them."""
    type_name = "deal_hole"

    def __init__(self, n: int, face_up: int = 0) -> None:
        super().__init__(n=n, face_up=face_up)
        self.n, self.face_up = n, face_up

    def apply(self, st, rng) -> None:
        new = []
        for p in range(st.n_players):
            cards = st.deal(self.n)
            new.append(cards)
            st.hole[p] = st.hole[p] + cards
        for p in range(st.n_players):
            st.emit("hole", p, visible=p, cards=tuple(st.hole[p]))
        if self.face_up:
            exposed = dict(st.extra.get("exposed", {}))     # copy: never mutate shared state
            for p in range(st.n_players):
                up = tuple(new[p][:self.face_up])
                exposed[p] = list(exposed.get(p, [])) + list(up)
                st.emit("expose", p, visible=ALL, cards=up)
            st.extra["exposed"] = exposed

    def describe(self) -> str:
        up = f", {self.face_up} face up" if self.face_up else ""
        return f"deal {self.n} hole card{'s' * (self.n != 1)} to each player{up}"


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
            st.muck += burned
            if self.burn_revealed:
                st.emit("burn", visible=ALL, cards=tuple(burned))
        st.board = st.board + st.deal(self.n)
        st.emit("board", visible=ALL, street=st.street, cards=tuple(st.board))

    def describe(self) -> str:
        burn = ""
        if self.burn:
            burn = f"burn {self.burn}{' face up' if self.burn_revealed else ''}, then "
        return f"{burn}deal {self.n} board card{'s' * (self.n != 1)} (new street)"
