"""Heads-up rules engine driven entirely by GameConfig (+ its special-step hooks).

Roles: role 0 = small blind (protocol seat 0), role 1 = big blind. Within a match the
small blind alternates every hand: player index (hand % 2) is the SB.

The deck for (seed, hand) is fixed, and cards are dealt by role (SB's hole cards first,
then BB's, then the board). Replaying a seed with the two players swapped therefore gives
each player exactly the cards the other had: duplicate poker.

The hand logic (`Hand`) is pure Python with no I/O; players are reached only through
`notify` / `act`. Bets are "raise TO" a total street contribution.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from bot.actions import (CALL, FOLD, RAISE, Action, LegalActions,
                         SpecialOption, is_legal, safe_action)
from bot.cards import DECK_SIZE
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, MatchEnd,
                          MatchInfo, OppAction, ProtocolError, Showdown, parse_action)
from lab.players import PlayerCrashed, PlayerTimeout
from variant.evaluator_hook import make_evaluator
from variant.rules import DEFAULT_CONFIG, GameConfig

SB, BB = 0, 1
ROLE_INDEX = {"SB": SB, "BB": BB}


class Forfeit(Exception):
    def __init__(self, role: int, reason: str) -> None:
        super().__init__(reason)
        self.role = role
        self.reason = reason


def deck_for(seed: int, hand_index: int) -> list[int]:
    """Deterministic shuffled deck for one hand of one seed."""
    return np.random.default_rng([seed, hand_index]).permutation(DECK_SIZE).tolist()


@dataclass
class HandResult:
    deltas: list[int]               # chip result per role
    showdown: bool
    folded: Optional[int]           # role that folded, if any
    pot: int


class Seat:
    """Per-player bookkeeping the engine keeps across a match."""

    def __init__(self, player, bank_s: float) -> None:
        self.player = player
        self.bank = bank_s
        self.errors = 0          # illegal / unparseable replies
        self.decisions = 0
        self.worst_decision_s = 0.0
        self.first_decision_s = 0.0      # includes process start-up overlap for subprocesses
        self.worst_after_first_s = 0.0


class Hand:
    """One hand. `seats[role]` gives the player for each role."""

    def __init__(self, cfg: GameConfig, seats: Sequence[Seat], stacks: Sequence[int],
                 deck: list[int], hand_id: int, evaluator, on_illegal: str = "fold") -> None:
        self.cfg = cfg
        self.seats = list(seats)
        self.start = list(stacks)
        self.stack = list(stacks)
        self.deck = list(deck)          # remaining cards, dealt from the front
        self.hand_id = hand_id
        self.ev = evaluator
        self.on_illegal = on_illegal
        self.hole: list[list[int]] = [[], []]
        self.board: list[int] = []
        self.street = 0
        self.bet = [0, 0]               # this street
        self.total = [0, 0]             # whole hand
        self.folded: Optional[int] = None
        self.last_raise = cfg.big_blind
        self.raises = 0

    # ---- helpers
    @property
    def pot(self) -> int:
        return self.total[0] + self.total[1]

    def deal(self, n: int) -> list[int]:
        cards, self.deck = self.deck[:n], self.deck[n:]
        return cards

    def pay(self, role: int, amount: int) -> None:
        amount = min(amount, self.stack[role])
        self.stack[role] -= amount
        self.bet[role] += amount
        self.total[role] += amount

    def notify(self, role: int, msg) -> None:
        try:
            self.seats[role].player.notify(msg)
        except PlayerCrashed as e:
            raise Forfeit(role, f"crash: {e}") from None

    def broadcast(self, msg) -> None:
        for r in (SB, BB):
            self.notify(r, msg)

    # ---- asking a player
    def ask(self, role: int, legal: LegalActions) -> Action:
        """Get a legal action from `role`, enforcing the time bank and illegal-reply policy."""
        seat = self.seats[role]
        req = ActRequest(self.pot, max(self.bet) - self.bet[role], self.stack[role],
                         self.stack[1 - role], legal, round(seat.bank, 4),
                         self.bet[role], self.bet[1 - role])
        t0 = time.perf_counter()
        try:
            raw = seat.player.act(req)
        except PlayerTimeout:
            seat.bank = 0.0
            raise Forfeit(role, "timeout") from None
        except PlayerCrashed as e:
            raise Forfeit(role, f"crash: {e}") from None
        dt = time.perf_counter() - t0
        seat.bank -= dt
        seat.decisions += 1
        seat.worst_decision_s = max(seat.worst_decision_s, dt)
        if seat.decisions == 1:
            seat.first_decision_s = dt
        else:
            seat.worst_after_first_s = max(seat.worst_after_first_s, dt)
        if seat.bank < 0:
            raise Forfeit(role, "time bank exhausted")
        try:
            action = parse_action(raw) if isinstance(raw, str) else raw
        except ProtocolError:
            action = None
        if action is None or not is_legal(action, legal):
            seat.errors += 1
            if self.on_illegal == "forfeit":
                raise Forfeit(role, f"illegal action {raw!r}")
            action = safe_action(legal)   # auto check/fold
        return action

    # ---- betting
    def legal_for(self, role: int) -> LegalActions:
        to_call = max(self.bet) - self.bet[role]
        stack, opp_stack = self.stack[role], self.stack[1 - role]
        cap = self.cfg.max_raises_per_street
        can_raise = stack > to_call and opp_stack > 0 and (cap is None or self.raises < cap)
        rmin = rmax = None
        if can_raise:
            rmax = self.bet[role] + stack                       # all-in
            rmin = min(max(self.bet) + max(self.last_raise, self.cfg.big_blind), rmax)
        return LegalActions(fold=to_call > 0, check=to_call == 0, call=to_call > 0,
                            raise_min=rmin, raise_max=rmax)

    def apply_bet(self, role: int, a: Action) -> None:
        if a.kind == FOLD:
            self.folded = role
        elif a.kind == CALL:
            self.pay(role, max(self.bet) - self.bet[role])
        elif a.kind == RAISE:
            prev_high = max(self.bet)
            self.pay(role, a.amount - self.bet[role])  # type: ignore[operator]
            increment = self.bet[role] - prev_high
            if increment >= self.last_raise:              # full raise reopens / sets size
                self.last_raise = increment
            self.raises += 1

    def betting_round(self) -> None:
        """Run one betting round; sets self.folded if someone folds."""
        cfg = self.cfg
        first = cfg.preflop_first_actor if self.street == 0 else cfg.postflop_first_actor
        actor = ROLE_INDEX[first]
        needs = {r for r in (SB, BB) if self.stack[r] > 0}
        # Nothing to decide if at most one player has chips and nobody faces a bet.
        if len(needs) < 2 and all(max(self.bet) == self.bet[r] for r in needs):
            return
        while needs:
            if actor in needs:
                a = self.ask(actor, self.legal_for(actor))
                self.apply_bet(actor, a)
                self.notify(1 - actor, OppAction(a))
                needs.discard(actor)
                if a.kind == FOLD:
                    return
                if a.kind == RAISE:
                    needs = {r for r in (SB, BB) if r != actor and self.stack[r] > 0}
            actor = 1 - actor

    # ---- special steps
    def run_special(self, step) -> None:
        for role_name in step.order:
            role = ROLE_INDEX[role_name]
            if self.folded is not None:
                return
            options = tuple(step.choices(self, role))
            if not options:
                continue
            legal = LegalActions(special=SpecialOption(step.name, options))
            a = self.ask(role, legal)
            board_before = list(self.board)
            step.apply(self, role, a.choice)
            self.notify(1 - role, OppAction(a))
            self.notify(role, HoleCards(tuple(self.hole[role])))
            if self.board != board_before:
                self.broadcast(BoardUpdate(self.street, tuple(self.board)))

    def specials(self, timing: str) -> None:
        for step in self.cfg.special_steps:
            if step.street == self.street and step.timing == timing:
                self.run_special(step)

    # ---- whole hand
    def play(self) -> HandResult:
        cfg = self.cfg
        for r in (SB, BB):
            self.notify(r, HandStart(self.hand_id, r, self.stack[r], self.stack[1 - r],
                                     round(self.seats[r].bank, 4)))
        self.pay(SB, cfg.small_blind)
        self.pay(BB, cfg.big_blind)
        for r in (SB, BB):
            self.hole[r] = self.deal(cfg.hole_cards)
        for r in (SB, BB):
            self.notify(r, HoleCards(tuple(self.hole[r])))

        for street, n_new in enumerate(cfg.streets):
            self.street = street
            if street > 0:
                self.bet = [0, 0]
                self.last_raise = cfg.big_blind
                self.raises = 0
                self.board += self.deal(n_new)
                self.broadcast(BoardUpdate(street, tuple(self.board)))
            self.specials("before_betting")
            if self.folded is None:
                self.betting_round()
            if self.folded is None:
                self.specials("after_betting")
            if self.folded is not None:
                break
        return self.settle()

    def settle(self) -> HandResult:
        pot = self.pot
        if self.folded is not None:
            winner = 1 - self.folded
            self.stack[winner] += pot
            showdown = False
        else:
            # Refund any uncalled excess (an all-in for less than the other's bet).
            matched = min(self.total)
            for r in (SB, BB):
                self.stack[r] += self.total[r] - matched
            vals = [self.ev.evaluate(self.hole[r], self.board) for r in (SB, BB)]
            share = 2 * matched
            if vals[0] > vals[1]:
                self.stack[SB] += share
            elif vals[1] > vals[0]:
                self.stack[BB] += share
            else:
                self.stack[SB] += share // 2
                self.stack[BB] += share - share // 2
            for r in (SB, BB):
                self.notify(r, Showdown(tuple(self.hole[1 - r])))
            showdown = True
        deltas = [self.stack[r] - self.start[r] for r in (SB, BB)]
        for r in (SB, BB):
            self.notify(r, HandEnd(deltas[r]))
        return HandResult(deltas, showdown, self.folded, pot)


# --------------------------------------------------------------------------- matches

@dataclass
class MatchResult:
    chips: list[int]                         # per player index
    hands_played: int
    errors: list[int]
    forfeit: Optional[int] = None            # player index that forfeited
    forfeit_reason: str = ""
    worst_decision_s: list[float] = field(default_factory=lambda: [0.0, 0.0])
    decisions: list[int] = field(default_factory=lambda: [0, 0])
    bank_left: list[float] = field(default_factory=lambda: [0.0, 0.0])
    first_decision_s: list[float] = field(default_factory=lambda: [0.0, 0.0])
    worst_after_first_s: list[float] = field(default_factory=lambda: [0.0, 0.0])
    hand_deltas: list[int] = field(default_factory=list)   # player 0's delta per hand

    def score(self, index: int) -> float:
        """Match points for player `index`: win 1, draw 0.5, loss 0."""
        if self.forfeit is not None:
            return 0.0 if self.forfeit == index else 1.0
        c = self.chips[index]
        return 1.0 if c > 0 else (0.5 if c == 0 else 0.0)


def play_match(players: Sequence, cfg: GameConfig = DEFAULT_CONFIG, seed: int = 0,
               hands: Optional[int] = None, on_illegal: str = "fold",
               evaluator=None, time_bank_s: Optional[float] = None) -> MatchResult:
    """Play one match between players[0] and players[1]. Player (h % 2) is SB in hand h."""
    hands = cfg.hands_per_match if hands is None else hands
    bank = cfg.time_bank_s if time_bank_s is None else time_bank_s
    ev = evaluator or make_evaluator(cfg)
    seats = [Seat(p, bank) for p in players]
    info = MatchInfo(hands, bank, cfg.small_blind, cfg.big_blind, cfg.starting_stack)
    stacks = [cfg.starting_stack, cfg.starting_stack]
    chips = [0, 0]
    result = MatchResult(chips, 0, [0, 0])
    try:
        for i in (0, 1):
            _safe_notify(seats, i, info)
        for h in range(hands):
            if not cfg.reset_stacks_each_hand and min(stacks) <= 0:
                break                                   # someone is bust
            sb_player = h % 2
            by_role = [seats[sb_player], seats[1 - sb_player]]
            role_stacks = ([cfg.starting_stack] * 2 if cfg.reset_stacks_each_hand
                           else [stacks[sb_player], stacks[1 - sb_player]])
            hand = Hand(cfg, by_role, role_stacks, deck_for(seed, h), h, ev, on_illegal)
            try:
                res = hand.play()
            except Forfeit as f:
                result.forfeit = sb_player if f.role == SB else 1 - sb_player
                result.forfeit_reason = f.reason
                break
            d = [res.deltas[SB], res.deltas[BB]] if sb_player == 0 else [res.deltas[BB], res.deltas[SB]]
            for i in (0, 1):
                chips[i] += d[i]
                stacks[i] += d[i]
            result.hand_deltas.append(d[0])
            result.hands_played += 1
        for i in (0, 1):
            _safe_notify(seats, i, MatchEnd())
    finally:
        for s in seats:
            try:
                s.player.close()
            except Exception:
                pass
    result.errors = [s.errors for s in seats]
    result.worst_decision_s = [s.worst_decision_s for s in seats]
    result.decisions = [s.decisions for s in seats]
    result.bank_left = [max(0.0, s.bank) for s in seats]
    result.first_decision_s = [s.first_decision_s for s in seats]
    result.worst_after_first_s = [s.worst_after_first_s for s in seats]
    return result


def _safe_notify(seats, i, msg) -> None:
    try:
        seats[i].player.notify(msg)
    except PlayerCrashed:
        pass
