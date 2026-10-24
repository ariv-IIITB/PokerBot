"""No-limit betting round ("raise TO" a total street contribution).

Rules: facing a bet you may fold, call (all-in for less is a call) or raise; with nothing
to call you may check or bet. The minimum raise is the previous full raise increment (at
least the big blind); an all-in for less than that is allowed but does not set a new
increment. Raising is impossible if the opponent is all-in or the raise cap is reached.
The round ends when every player with chips has acted since the last raise.
"""
from __future__ import annotations

from typing import Optional

from bot.actions import CALL, FOLD, RAISE, Action, LegalActions
from bot.game.state import ALL
from bot.game.steps.base import Step

ROLE = {"SB": 0, "BB": 1}


class _Progress:
    __slots__ = ("actor", "needs")

    def __init__(self, actor: int, needs: set) -> None:
        self.actor, self.needs = actor, needs

    def copy(self) -> "_Progress":
        return _Progress(self.actor, set(self.needs))


class Betting(Step):
    type_name = "betting"
    decision = True

    def __init__(self, first_actor: str = "BB", max_raises: Optional[int] = None,
                 big_blind: int = 2, label: str = "") -> None:
        super().__init__(first_actor=first_actor, max_raises=max_raises, label=label)
        self.first = ROLE[first_actor]
        self.max_raises = max_raises
        self.bb = big_blind
        self.label = label

    def begin(self, st) -> None:
        if st.rounds_done > 0:                  # later rounds start from zero bets
            st.bet = [0] * st.n_players
            st.last_raise = self.bb
            st.raises = 0
        needs = {p for p in range(st.n_players) if st.stack[p] > 0}
        # Nothing to decide if at most one player has chips and nobody faces a bet.
        if len(needs) < 2 and all(st.to_call(p) == 0 for p in needs):
            needs = set()
        st.step_state = _Progress(self.first, needs)

    def next_actor(self, st) -> Optional[int]:
        prog: _Progress = st.step_state
        if st.folded is not None:
            return None
        for _ in range(st.n_players):
            if prog.actor in prog.needs:
                return prog.actor
            prog.actor = (prog.actor + 1) % st.n_players
        return None

    def legal(self, st, p: int) -> LegalActions:
        to_call = st.to_call(p)
        stack = st.stack[p]
        opp_has_chips = any(st.stack[q] > 0 for q in range(st.n_players) if q != p)
        capped = self.max_raises is not None and st.raises >= self.max_raises
        rmin = rmax = None
        if stack > to_call and opp_has_chips and not capped:
            rmax = st.bet[p] + stack
            rmin = min(max(st.bet) + max(st.last_raise, self.bb), rmax)
        return LegalActions(fold=to_call > 0, check=to_call == 0, call=to_call > 0,
                            raise_min=rmin, raise_max=rmax)

    def apply_choice(self, st, p: int, a: Action) -> None:
        prog: _Progress = st.step_state
        if a.kind == FOLD:
            st.folded = p
        elif a.kind == CALL:
            st.pay(p, st.to_call(p))
        elif a.kind == RAISE:
            prev_high = max(st.bet)
            st.pay(p, a.amount - st.bet[p])
            increment = st.bet[p] - prev_high
            if increment >= st.last_raise:     # a full raise sets the new increment
                st.last_raise = increment
            st.raises += 1
        st.emit("action", p, visible=ALL, action=a)
        prog.needs.discard(p)
        if a.kind == RAISE:
            prog.needs = {q for q in range(st.n_players) if q != p and st.stack[q] > 0}
        elif a.kind == FOLD:
            prog.needs = set()
        prog.actor = (p + 1) % st.n_players

    def end(self, st) -> None:
        st.rounds_done += 1

    def describe(self) -> str:
        cap = f", max {self.max_raises} raises" if self.max_raises is not None else ""
        name = f"{self.label} " if self.label else ""
        return f"{name}no-limit betting, {self.params['first_actor']} acts first{cap}"
