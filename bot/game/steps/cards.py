"""Card-manipulation steps: discard, draw, swap, choose, peek, expose.

All share `CardStep`, which handles:
  order       "BB_first" | "SB_first" | "simultaneous" (both choose before anything is
              applied or shown, so the second chooser learns nothing from the first)
  options     finite choice strings, offered as LegalActions.special:
                "0", "0+2"  hole-card indices (into the player's current hole cards)
                "none"      do nothing (optional steps; listed first, so Tier 0 skips)
                "yes"/"no"  peeks
                "h1b3"      swap hole card 1 with board card 3
  cost        chips paid into the pot (not a bet) for any action other than "none"/"no";
              players who can't afford it only get the free option
  visibility  what the opponent learns: "public" (the cards), "private" (only that the
              step happened, as choice "hidden"), "later" (the cards at showdown)

Every card move keeps the deck + holes + board + muck a permutation of the starting deck.
"""
from __future__ import annotations

import itertools
from typing import Optional

from bot.actions import Action, LegalActions, SpecialOption
from bot.game.state import ALL
from bot.game.steps.base import Step

ORDERS = {"BB_first": [1, 0], "SB_first": [0, 1], "simultaneous": [0, 1]}
HIDDEN = "hidden"


def idx_choice(indices) -> str:
    return "+".join(str(i) for i in indices) if indices else "none"


def parse_idx(choice: str) -> list[int]:
    return [] if choice in ("none", "") else [int(x) for x in choice.split("+")]


class _Pending:
    __slots__ = ("order", "options", "chosen")

    def __init__(self, order: list[int]) -> None:
        self.order, self.options, self.chosen = order, (), []

    def copy(self) -> "_Pending":
        q = _Pending(list(self.order))
        q.options, q.chosen = self.options, list(self.chosen)
        return q


class CardStep(Step):
    """Base for card steps. Subclasses implement options() and perform()."""
    decision = True
    free_choices = ("none", "no")

    def __init__(self, order: str = "BB_first", cost: int = 0, visibility: str = "public",
                 **params) -> None:
        super().__init__(order=order, cost=cost, visibility=visibility, **params)
        if order not in ORDERS:
            raise ValueError(f"unknown order {order!r}")
        self.order, self.cost, self.visibility = order, cost, visibility
        self.simultaneous = order == "simultaneous"

    # ---- to implement
    def options(self, st, p: int) -> tuple[str, ...]:
        """Choice strings for player p ( () = no decision for p)."""
        raise NotImplementedError

    def perform(self, st, p: int, choice: str) -> None:
        """Apply p's choice: move cards and emit card/hole/board events."""
        raise NotImplementedError

    def auto_choice(self, st, p: int) -> Optional[str]:
        """For steps without a real decision (random modes): the choice to apply."""
        return None

    # ---- shared machinery
    def begin(self, st) -> None:
        st.step_state = _Pending(list(ORDERS[self.order]))

    def affordable(self, st, p: int, opts: tuple[str, ...]) -> tuple[str, ...]:
        if self.cost and st.stack[p] < self.cost:
            return tuple(o for o in opts if o in self.free_choices)
        return opts

    def next_actor(self, st) -> Optional[int]:
        q: _Pending = st.step_state
        while q.order:
            p = q.order[0]
            auto = self.auto_choice(st, p)
            if auto is not None:
                q.order.pop(0)
                self._commit(st, p, auto, decided=False)
                continue
            opts = self.affordable(st, p, self.options(st, p))
            if not opts:
                q.order.pop(0)
                continue
            q.options = opts
            return p
        for p, choice, decided in q.chosen:     # simultaneous: apply everything at the end
            self._apply(st, p, choice, decided)
        q.chosen = []
        return None

    def legal(self, st, p: int) -> LegalActions:
        return LegalActions(special=SpecialOption(self.type_name, st.step_state.options))

    def apply_choice(self, st, p: int, a: Action) -> None:
        q: _Pending = st.step_state
        q.order.pop(0)
        self._commit(st, p, a.choice)

    def _commit(self, st, p: int, choice: str, decided: bool = True) -> None:
        if self.simultaneous:
            st.step_state.chosen.append((p, choice, decided))
        else:
            self._apply(st, p, choice, decided)

    def _apply(self, st, p: int, choice: str, decided: bool = True) -> None:
        if self.cost and choice not in self.free_choices:
            st.pay_cost(p, self.cost)
        if decided:              # random outcomes aren't anyone's choice: shown by effects only
            self.announce(st, p, choice)
        self.perform(st, p, choice)

    def announce(self, st, p: int, choice: str) -> None:
        """Tell both players what was chosen (the opponent gets 'hidden' when private)."""
        st.emit("special", p, visible=p, action=Action.special(choice))
        shown = choice if self.visibility == "public" else HIDDEN
        for q in range(st.n_players):
            if q != p:
                st.emit("special", p, visible=q, action=Action.special(shown))

    # ---- helpers for subclasses
    def show_hole(self, st, p: int) -> None:
        st.emit("hole", p, visible=p, cards=tuple(st.hole[p]))

    def show_board(self, st) -> None:
        st.emit("board", visible=ALL, street=st.street, cards=tuple(st.board))

    def reveal(self, st, p: int, cards, what: str) -> None:
        """Make cards that left p's hand known per visibility (public now / at showdown)."""
        if not cards:
            return
        if self.visibility == "public":
            st.emit("reveal", p, visible=ALL, cards=tuple(cards), what=what)
        elif self.visibility == "later":
            later = dict(st.extra.get("reveal_later", {}))
            later[p] = tuple(later.get(p, ())) + tuple(cards)
            st.extra["reveal_later"] = later


class Discard(CardStep):
    """Each player discards `n` hole cards. destination: "board" (face up onto the board),
    "muck", or "opponent" (the opponent receives them). optional: may discard nothing."""
    type_name = "discard"

    def __init__(self, n: int = 1, destination: str = "board", optional: bool = False,
                 **kw) -> None:
        super().__init__(n=n, destination=destination, optional=optional, **kw)
        self.n, self.destination, self.optional = n, destination, optional

    def options(self, st, p: int) -> tuple[str, ...]:
        h = len(st.hole[p])
        if h < self.n:
            return ()
        opts = tuple(idx_choice(c) for c in itertools.combinations(range(h), self.n))
        return (("none",) + opts) if self.optional else opts

    def perform(self, st, p: int, choice: str) -> None:
        idx = parse_idx(choice)
        cards = [st.hole[p][i] for i in idx]
        st.hole[p] = [c for i, c in enumerate(st.hole[p]) if i not in idx]
        self.show_hole(st, p)
        if not cards:
            return
        if self.destination == "board":
            st.board = st.board + cards
            self.show_board(st)
        elif self.destination == "opponent":
            q = 1 - p
            st.hole[q] = st.hole[q] + cards
            self.show_hole(st, q)
            self.reveal(st, p, cards, "discard")
        else:
            st.muck += cards
            self.reveal(st, p, cards, "discard")

    def describe(self) -> str:
        opt = "may discard" if self.optional else "discards"
        return (f"each player ({self.order.replace('_', ' ')}) {opt} {self.n} hole card(s) "
                f"to the {self.destination}, {self.visibility}")


class Draw(CardStep):
    """Each player may replace between `min` and `max` hole cards with new cards from the
    deck (discards go to the muck). The number drawn is always public."""
    type_name = "draw"

    def __init__(self, max: int = 1, min: int = 0, **kw) -> None:
        kw.setdefault("visibility", "private")
        super().__init__(max=max, min=min, **kw)
        self.max, self.min = max, min

    def options(self, st, p: int) -> tuple[str, ...]:
        h = len(st.hole[p])
        top = min(self.max, h, len(st.deck))
        return tuple(idx_choice(c) for k in range(self.min, top + 1)
                     for c in itertools.combinations(range(h), k))

    def announce(self, st, p: int, choice: str) -> None:
        st.emit("special", p, visible=p, action=Action.special(choice))
        shown = choice if self.visibility == "public" else str(len(parse_idx(choice)))
        st.emit("special", p, visible=1 - p, action=Action.special(shown))

    def perform(self, st, p: int, choice: str) -> None:
        idx = parse_idx(choice)
        out = [st.hole[p][i] for i in idx]
        keep = [c for i, c in enumerate(st.hole[p]) if i not in idx]
        st.muck += out
        st.hole[p] = keep + st.deal(len(out))
        self.show_hole(st, p)
        self.reveal(st, p, out, "draw")

    def describe(self) -> str:
        cost = f" for {self.cost} chips" if self.cost else ""
        return f"each player may draw {self.min}-{self.max} replacement card(s){cost}"


class Swap(CardStep):
    """Swap one hole card with: the opponent (a random card of theirs), the board (a chosen
    board card), or the deck (the top card). mode: "optional" (may pass), "forced" (must
    choose), "random" (no decision: a random card, and it only happens with `probability`)."""
    type_name = "swap"

    def __init__(self, target: str = "opponent", mode: str = "optional",
                 probability: float = 1.0, **kw) -> None:
        super().__init__(target=target, mode=mode, probability=probability, **kw)
        self.target, self.mode, self.probability = target, mode, probability

    def options(self, st, p: int) -> tuple[str, ...]:
        h = len(st.hole[p])
        if h == 0:
            return ()
        if self.target == "board":
            opts = tuple(f"h{i}b{j}" for i in range(h) for j in range(len(st.board)))
        else:
            if self.target == "opponent" and not st.hole[1 - p]:
                return ()
            if self.target == "deck" and not st.deck:
                return ()
            opts = tuple(str(i) for i in range(h))
        if not opts:
            return ()
        return (("none",) + opts) if self.mode == "optional" else opts

    def auto_choice(self, st, p: int) -> Optional[str]:
        if self.mode != "random":
            return None
        opts = self.options(st, p)
        if not opts or st.random().random() >= self.probability:
            return "none"
        return opts[int(st.random().integers(len(opts)))]

    def perform(self, st, p: int, choice: str) -> None:
        if choice == "none":
            return
        if self.target == "board":
            i, j = (int(x) for x in choice[1:].split("b"))
            st.hole[p][i], st.board[j] = st.board[j], st.hole[p][i]
            st.hole[p] = list(st.hole[p])
            self.show_hole(st, p)
            self.show_board(st)
            return
        i = int(choice)
        if self.target == "deck":
            st.muck.append(st.hole[p][i])
            st.hole[p] = [c for k, c in enumerate(st.hole[p]) if k != i] + st.deal(1)
            self.show_hole(st, p)
            return
        q = 1 - p
        j = int(st.random().integers(len(st.hole[q])))
        mine, theirs = st.hole[p][i], st.hole[q][j]
        st.hole[p] = [c for k, c in enumerate(st.hole[p]) if k != i] + [theirs]
        st.hole[q] = [c for k, c in enumerate(st.hole[q]) if k != j] + [mine]
        self.show_hole(st, p)
        self.show_hole(st, q)

    def describe(self) -> str:
        how = {"optional": "may swap", "forced": "must swap", "random": "randomly swaps"}[self.mode]
        return f"each player {how} one hole card with the {self.target}"


class Choose(CardStep):
    """Each player is privately offered `offer` cards and keeps `keep` of them as hole
    cards; the rest are mucked."""
    type_name = "choose"

    def __init__(self, offer: int = 3, keep: int = 1, **kw) -> None:
        kw.setdefault("visibility", "private")
        super().__init__(offer=offer, keep=keep, **kw)
        self.offer, self.keep = offer, keep

    def begin(self, st) -> None:
        super().begin(st)
        offers = {}
        for p in range(st.n_players):
            offers[p] = tuple(st.deal(self.offer))
            st.emit("offer", p, visible=p, cards=offers[p])
        st.extra["offers"] = offers

    def options(self, st, p: int) -> tuple[str, ...]:
        n = len(st.extra["offers"][p])
        return tuple(idx_choice(c) for c in itertools.combinations(range(n), min(self.keep, n)))

    def perform(self, st, p: int, choice: str) -> None:
        offered = st.extra["offers"][p]
        idx = parse_idx(choice)
        st.hole[p] = st.hole[p] + [offered[i] for i in idx]
        rest = [c for i, c in enumerate(offered) if i not in idx]
        st.muck += rest
        st.extra["offers"] = {q: o for q, o in st.extra["offers"].items() if q != p}  # consumed
        self.show_hole(st, p)
        self.reveal(st, p, rest, "unchosen")

    def end(self, st) -> None:
        st.extra.pop("offers", None)

    def describe(self) -> str:
        return f"each player is offered {self.offer} cards and keeps {self.keep}"


class Peek(CardStep):
    """A player may pay `cost` to see the next card off the deck ("board": the next card
    that will be dealt, if no burn) or one random hole card of the opponent's."""
    type_name = "peek"

    def __init__(self, target: str = "board", **kw) -> None:
        super().__init__(target=target, **kw)
        self.target = target

    def options(self, st, p: int) -> tuple[str, ...]:
        if self.target == "board" and not st.deck:
            return ()
        if self.target == "opponent" and not st.hole[1 - p]:
            return ()
        return ("no", "yes")

    def perform(self, st, p: int, choice: str) -> None:
        if choice != "yes":
            return
        if self.target == "board":
            card = st.deck[0]
        else:
            opp = st.hole[1 - p]
            card = opp[int(st.random().integers(len(opp)))]
        st.emit("peek", 1 - p if self.target == "opponent" else -1, visible=p, cards=(card,),
                target=self.target)

    def describe(self) -> str:
        cost = f" for {self.cost} chips" if self.cost else ""
        what = "the next deck card" if self.target == "board" else "a random opponent hole card"
        return f"each player may peek at {what}{cost}"


class Expose(CardStep):
    """Each player shows `n` hole cards face up: chosen by the player, or at random."""
    type_name = "expose"

    def __init__(self, n: int = 1, chosen: bool = True, **kw) -> None:
        super().__init__(n=n, chosen=chosen, **kw)
        self.n, self.chosen = n, chosen

    def options(self, st, p: int) -> tuple[str, ...]:
        h = len(st.hole[p])
        if h < self.n:
            return ()
        return tuple(idx_choice(c) for c in itertools.combinations(range(h), self.n))

    def auto_choice(self, st, p: int) -> Optional[str]:
        if self.chosen:
            return None
        opts = self.options(st, p)
        return opts[int(st.random().integers(len(opts)))] if opts else "none"

    def perform(self, st, p: int, choice: str) -> None:
        cards = tuple(st.hole[p][i] for i in parse_idx(choice))
        if cards:
            exposed = dict(st.extra.get("exposed", {}))
            exposed[p] = list(exposed.get(p, [])) + list(cards)
            st.extra["exposed"] = exposed
            st.emit("expose", p, visible=ALL, cards=cards)

    def describe(self) -> str:
        how = "chosen" if self.chosen else "random"
        return f"each player exposes {self.n} {how} hole card(s) face up"
