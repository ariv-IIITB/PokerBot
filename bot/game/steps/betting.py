"""Betting round plugin: no-limit, pot-limit and fixed-limit, "raise TO" amounts.

Rules (all structures): facing a bet you may fold, call (all-in for less is a call) or
raise; with nothing to call you may check or bet. Raising is impossible if the opponent is
all-in or the raise cap is reached. An all-in for less than a full raise is allowed but
doesn't set a new raise increment. The round ends when every player with chips has acted
since the last raise.

  NL  min raise-to = current bet + max(last full raise, big blind); max = all-in
  PL  max raise-to = current bet + (pot after calling)     i.e.  bet + pot + to_call
  FL  the only raise-to = current bet + fixed size for this round (cap default 4)
Optional restrictions:
  bet_sizes      raise-to must be current bet + f x (pot after calling) for f in the list
                 (or all-in), snapped into the legal range
  bet_multiple   raise-to amounts must be multiples of this (or all-in)
  check_raise    False: a player who checked this round may not raise later in it
  blind_counts_as_raise  the first round starts with one raise used (the big blind), so
                 max_raises 4 allows 3 voluntary preflop raises and 4 per later round
"""
from __future__ import annotations

from typing import Optional

from bot.actions import CALL, CHECK, FOLD, RAISE, Action, LegalActions
from bot.game.state import ALL
from bot.game.steps.base import Step

ROLE = {"SB": 0, "BB": 1}


class _Progress:
    __slots__ = ("actor", "needs", "checked")

    def __init__(self, actor: int, needs: set) -> None:
        self.actor, self.needs, self.checked = actor, needs, set()

    def copy(self) -> "_Progress":
        p = _Progress(self.actor, set(self.needs))
        p.checked = set(self.checked)
        return p


class Betting(Step):
    type_name = "betting"
    decision = True

    def __init__(self, first_actor: str = "BB", max_raises: Optional[int] = None,
                 big_blind: int = 2, label: str = "", structure: str = "NL",
                 fixed_bet: Optional[int] = None, bet_sizes: Optional[tuple] = None,
                 bet_multiple: Optional[int] = None, check_raise: bool = True,
                 blind_counts_as_raise: bool = False) -> None:
        if structure == "FL" and max_raises is None:
            max_raises = 4
        super().__init__(first_actor=first_actor, max_raises=max_raises, label=label,
                         structure=structure)
        if structure not in ("NL", "PL", "FL"):
            raise ValueError(f"unknown betting structure {structure!r}")
        if structure == "FL" and not fixed_bet:
            raise ValueError("fixed-limit betting needs a fixed bet size")
        self.first = ROLE[first_actor]
        self.max_raises = max_raises
        self.bb = big_blind
        self.label = label
        self.structure = structure
        self.fixed_bet = fixed_bet
        self.bet_sizes = tuple(bet_sizes) if bet_sizes else None
        self.bet_multiple = bet_multiple
        self.check_raise = check_raise
        self.blind_raise = blind_counts_as_raise

    @classmethod
    def from_spec(cls, s, ctx):
        from bot.game.rules_spec import street_label
        b, i = ctx.spec.betting, ctx.round_index
        default_first = ("BB" if b.straddle else b.preflop_first) if i == 0 else b.postflop_first
        fixed = b.fixed_bets[i] if b.structure == "FL" else None
        return cls(s.get("first") or default_first, b.max_raises, b.big_blind,
                   s.get("round") or street_label(i), structure=b.structure, fixed_bet=fixed,
                   bet_sizes=b.bet_sizes, bet_multiple=b.bet_multiple, check_raise=b.check_raise,
                   blind_counts_as_raise=b.blind_counts_as_raise and i == 0)

    def _bb(self, st) -> int:
        return st.level[1] if st.level else self.bb

    def begin(self, st) -> None:
        if st.rounds_done > 0:                  # later rounds start from zero bets
            st.bet = [0] * st.n_players
            st.last_raise = self._bb(st)
            st.raises = 0
        elif self.blind_raise:                  # the big blind is the first raise of the cap
            st.raises = 1
        needs = {p for p in range(st.n_players) if st.stack[p] > 0}
        # Nothing to decide if at most one player has chips and nobody faces a bet.
        if len(needs) < 2 and all(st.to_call(p) == 0 for p in needs):
            needs = set()
        first = self.first
        winner = st.extra.get("position_winner")       # auction prize: act last postflop
        if winner is not None and st.rounds_done > 0:
            first = (winner + 1) % st.n_players
        st.step_state = _Progress(first, needs)

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
        high = max(st.bet)
        all_in = st.bet[p] + stack
        opp_has_chips = any(st.stack[q] > 0 for q in range(st.n_players) if q != p)
        capped = self.max_raises is not None and st.raises >= self.max_raises
        no_cr = not self.check_raise and p in st.step_state.checked
        rmin = rmax = None
        sizes = step = None
        if stack > to_call and opp_has_chips and not capped and not no_cr:
            if self.structure == "FL":
                rmin = rmax = min(high + self.fixed_bet, all_in)
            else:
                rmin = high + max(st.last_raise, self._bb(st))
                rmax = all_in
                if self.structure == "PL":
                    rmax = min(all_in, high + st.pot + to_call)
                rmin = min(rmin, rmax)
                if self.bet_sizes:
                    pot_after = st.pot + to_call
                    sizes = sorted({min(max(int(round(high + f * pot_after)), rmin), rmax)
                                    for f in self.bet_sizes} | {rmax})
                    sizes = tuple(sizes)
                    rmin, rmax = sizes[0], sizes[-1]
                elif self.bet_multiple:
                    m = self.bet_multiple
                    up = -(-rmin // m) * m
                    rmin = up if up <= rmax else rmax
                    step = m
        return LegalActions(fold=to_call > 0, check=to_call == 0, call=to_call > 0,
                            raise_min=rmin, raise_max=rmax, raise_sizes=sizes, raise_step=step)

    def apply_choice(self, st, p: int, a: Action) -> None:
        prog: _Progress = st.step_state
        if a.kind == FOLD:
            st.folded = p
        elif a.kind == CHECK:
            prog.checked.add(p)
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
        # Remember where the board stood when an all-in closed the action ("run it twice").
        if (st.folded is None and "allin_cut" not in st.extra
                and any(st.stack[p] == 0 for p in range(st.n_players))):
            st.extra["allin_cut"] = (len(st.board), tuple(len(b) for b in st.boards))

    def describe(self) -> str:
        cap = f", max {self.max_raises} raises" if self.max_raises is not None else ""
        cap += " (the big blind counts as one)" if self.blind_raise else ""
        name = f"{self.label} " if self.label else ""
        kind = {"NL": "no-limit", "PL": "pot-limit",
                "FL": f"fixed-limit ({self.fixed_bet})"}[self.structure]
        extra = ""
        if self.bet_sizes:
            extra += f", sizes {list(self.bet_sizes)} x pot"
        if self.bet_multiple:
            extra += f", multiples of {self.bet_multiple}"
        if not self.check_raise:
            extra += ", no check-raise"
        return f"{name}{kind} betting, {self.params['first_actor']} acts first{cap}{extra}"
