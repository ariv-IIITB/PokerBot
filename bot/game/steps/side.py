"""Side mechanics: bounty ranks, sealed-bid auctions and a side market.

bounty   A rank that pays extra when you win the pot outright at showdown holding a hole
         card of that rank (see payoffs.py). mode: "random" (one rank for both, shown to
         both), "fixed" (`rank`), "chosen" (each player privately picks their own rank;
         shown at showdown).
auction  Sealed simultaneous bids (0..max_bid, capped by stack) for a prize:
           card      the winner gets one extra hole card
           peek      the winner sees the next card off the deck
           position  the winner acts last in every later betting round
           swap      the winner may swap one hole card with the top of the deck
         kind: "first_price" (winner pays own bid), "second_price" (winner pays the loser's
         bid), "all_pay" (both pay their own bids). payment: "pot", "opponent" (to the other
         player), "burn" (to the house). tie: "BB", "SB", "random" or "none" (no sale).
         Both bids are revealed after the auction.
market   Both players quote a price for a quantity of the final board (simultaneous). The
         higher quote buys `size` units from the lower at the midpoint; at the end of the
         hand the buyer gains size x scale x (value - price) from the seller. Equal quotes:
         no trade. Quotes are revealed after both are in.
"""
from __future__ import annotations

from typing import Optional

from bot.actions import Action, LegalActions, SpecialOption
from bot.cards import RANKS
from bot.game.payoffs import market_range
from bot.game.state import ALL
from bot.game.steps.base import Step
from bot.game.steps.cards import CardStep


class Bounty(CardStep):
    type_name = "bounty"

    def __init__(self, mode: str = "random", rank: Optional[str] = None, bonus: int = 0,
                 multiplier: float = 1.0, ranks: str = RANKS) -> None:
        super().__init__(order="simultaneous", visibility="private", mode=mode, rank=rank,
                         bonus=bonus, multiplier=multiplier)
        if mode not in ("random", "fixed", "chosen"):
            raise ValueError(f"unknown bounty mode {mode!r}")
        if mode == "fixed" and (rank is None or rank not in RANKS):
            raise ValueError("fixed bounty needs a rank symbol")
        self.mode, self.rank, self.bonus, self.multiplier = mode, rank, bonus, multiplier
        self.deck_ranks = ranks

    def begin(self, st) -> None:
        super().begin(st)
        base = {"ranks": {}, "bonus": self.bonus, "multiplier": self.multiplier,
                "hidden": self.mode == "chosen"}
        if self.mode != "chosen":
            if self.mode == "random":
                sym = self.deck_ranks[int(st.random().integers(len(self.deck_ranks)))]
            else:
                sym = self.rank
            r = RANKS.index(sym)
            base["ranks"] = {p: r for p in range(st.n_players)}
            st.emit("bounty", -1, visible=ALL, value=r, cards=())
        st.extra["bounty"] = base

    def options(self, st, p: int) -> tuple[str, ...]:
        return tuple(self.deck_ranks) if self.mode == "chosen" else ()

    def perform(self, st, p: int, choice: str) -> None:
        bounty = dict(st.extra["bounty"])
        bounty["ranks"] = dict(bounty["ranks"])
        bounty["ranks"][p] = RANKS.index(choice)
        st.extra["bounty"] = bounty
        st.emit("bounty", p, visible=p, value=RANKS.index(choice), cards=())

    def describe(self) -> str:
        pay = f"+{self.bonus}" if self.bonus else ""
        pay += f" x{self.multiplier:g}" if self.multiplier != 1 else ""
        return f"bounty rank ({self.mode}) pays {pay or 'nothing'} to an outright showdown winner"


class _AuctionState:
    __slots__ = ("bids", "order", "options", "chosen", "swap_for")

    def __init__(self) -> None:
        self.bids: dict = {}
        self.order = [0, 1]
        self.options = None
        self.chosen: list = []
        self.swap_for: Optional[int] = None

    def copy(self) -> "_AuctionState":
        a = _AuctionState()
        a.bids, a.order, a.options = dict(self.bids), list(self.order), self.options
        a.chosen, a.swap_for = list(self.chosen), self.swap_for
        return a


class Auction(Step):
    type_name = "auction"
    decision = True

    def __init__(self, kind: str = "second_price", prize: str = "card", payment: str = "pot",
                 tie: str = "BB", max_bid: Optional[int] = None) -> None:
        super().__init__(kind=kind, prize=prize, payment=payment, tie=tie, max_bid=max_bid)
        if kind not in ("first_price", "second_price", "all_pay"):
            raise ValueError(f"unknown auction kind {kind!r}")
        if prize not in ("card", "peek", "position", "swap"):
            raise ValueError(f"unknown auction prize {prize!r}")
        if payment not in ("pot", "opponent", "burn"):
            raise ValueError(f"unknown auction payment {payment!r}")
        self.kind, self.prize, self.payment, self.tie, self.max_bid = kind, prize, payment, tie, max_bid

    def begin(self, st) -> None:
        st.step_state = _AuctionState()

    def cap(self, st, p: int) -> int:
        return st.stack[p] if self.max_bid is None else min(st.stack[p], self.max_bid)

    def next_actor(self, st) -> Optional[int]:
        a: _AuctionState = st.step_state
        if a.swap_for is not None:
            return a.swap_for
        if a.order:
            return a.order[0]
        return None

    def legal(self, st, p: int) -> LegalActions:
        a: _AuctionState = st.step_state
        if a.swap_for is not None:
            opts = ("none",) + tuple(str(i) for i in range(len(st.hole[p])))
            return LegalActions(special=SpecialOption("swap", opts))
        return LegalActions(special=SpecialOption("bid", (), 0, self.cap(st, p)))

    def apply_choice(self, st, p: int, action: Action) -> None:
        a: _AuctionState = st.step_state
        if a.swap_for is not None:                       # the winner's swap prize
            a.swap_for = None
            if action.choice != "none" and st.deck:
                i = int(action.choice)
                st.muck.append(st.hole[p][i])
                st.hole[p] = [c for k, c in enumerate(st.hole[p]) if k != i] + st.deal(1)
                st.emit("hole", p, visible=p, cards=tuple(st.hole[p]))
            st.emit("special", p, visible=p, action=action)
            st.emit("special", p, visible=1 - p, action=Action.special("hidden"))
            return
        a.order.pop(0)
        a.bids[p] = min(int(action.choice), self.cap(st, p))
        if not a.order:
            self.resolve(st)

    def resolve(self, st) -> None:
        bids = st.step_state.bids
        for p in range(st.n_players):                    # sealed bids revealed together
            for q in range(st.n_players):
                if q != p:
                    st.emit("special", p, visible=q, action=Action.special(str(bids[p])))
        b0, b1 = bids[0], bids[1]
        if b0 != b1:
            winner = 0 if b0 > b1 else 1
        elif self.tie == "BB":
            winner = 1
        elif self.tie == "SB":
            winner = 0
        elif self.tie == "random":
            winner = int(st.random().integers(2))
        else:
            winner = None
        if winner is None:
            st.emit("auction", -1, visible=ALL, value=0, cards=())
            return
        loser = 1 - winner
        pays = {"first_price": {winner: bids[winner]},
                "second_price": {winner: bids[loser]},
                "all_pay": {winner: bids[winner], loser: bids[loser]}}[self.kind]
        for p, amount in pays.items():
            self.pay(st, p, amount)
        st.emit("auction", winner, visible=ALL, value=pays.get(winner, 0), cards=())
        self.award(st, winner)

    def pay(self, st, p: int, amount: int) -> None:
        amount = max(0, min(amount, st.stack[p]))
        if not amount:
            return
        if self.payment == "pot":
            st.pay_cost(p, amount)
        elif self.payment == "opponent":
            st.stack[p] -= amount
            st.stack[1 - p] += amount
        else:
            st.stack[p] -= amount
            st.house += amount

    def award(self, st, w: int) -> None:
        if self.prize == "card" and st.deck:
            st.hole[w] = st.hole[w] + st.deal(1)
            st.emit("hole", w, visible=w, cards=tuple(st.hole[w]))
        elif self.prize == "peek" and st.deck:
            st.emit("peek", -1, visible=w, cards=(st.deck[0],), target="board")
        elif self.prize == "position":
            st.extra["position_winner"] = w
        elif self.prize == "swap" and st.hole[w]:
            st.step_state.swap_for = w

    def describe(self) -> str:
        return (f"sealed {self.kind.replace('_', '-')} auction for {self.prize}; bids to "
                f"{self.payment}; ties: {self.tie}")


class Market(CardStep):
    type_name = "market"

    def __init__(self, quantity: str = "board_rank_sum", size: int = 1, settle_scale: float = 1,
                 board_cards: int = 5) -> None:
        super().__init__(order="simultaneous", visibility="public", quantity=quantity,
                         size=size, settle_scale=settle_scale)
        self.quantity, self.size, self.scale = quantity, size, settle_scale
        self.lo, self.hi = market_range(quantity, board_cards)

    def options(self, st, p: int) -> tuple[str, ...]:
        return ("quote",)            # placeholder: legal() offers a numeric range instead

    def legal(self, st, p: int) -> LegalActions:
        return LegalActions(special=SpecialOption("quote", (), self.lo, self.hi))

    def apply_choice(self, st, p: int, a: Action) -> None:
        q = st.step_state
        q.order.pop(0)
        v = min(max(int(a.choice), self.lo), self.hi)
        q.chosen.append((p, str(v)))

    def next_actor(self, st):
        q = st.step_state
        if q.order:
            return q.order[0]
        if q.chosen:
            quotes = {p: int(c) for p, c in q.chosen}
            q.chosen = []
            for p in quotes:
                for o in quotes:
                    if o != p:
                        st.emit("special", p, visible=o, action=Action.special(str(quotes[p])))
            if quotes[0] != quotes[1]:
                buyer = 0 if quotes[0] > quotes[1] else 1
                st.extra["market"] = {"buyer": buyer, "seller": 1 - buyer,
                                      "price": (quotes[0] + quotes[1]) / 2, "size": self.size,
                                      "scale": self.scale, "quantity": self.quantity}
        return None

    def perform(self, st, p: int, choice: str) -> None:   # not used: quotes resolve together
        pass

    def describe(self) -> str:
        return (f"side market on {self.quantity.replace('_', ' ')} ({self.lo}-{self.hi}): "
                f"higher quote buys {self.size} unit(s) at the midpoint")
