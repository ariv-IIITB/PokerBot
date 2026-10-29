"""Heads-up rules engine driven entirely by a variant spec (compiled into bot.game Rules).

Roles: role 0 = small blind (protocol seat 0), role 1 = big blind. Within a match the
small blind alternates every hand: player index (hand % 2) is the SB.

The deck for (seed, hand) is fixed, and cards are dealt by role (SB's hole cards first,
then BB's, then the board). Replaying a seed with the two players swapped therefore gives
each player exactly the cards the other had: duplicate poker.

The rules themselves live in bot/game/ (shared with the bot, which can simulate them);
`Hand` drives a bot.game.GameState and turns its events into protocol messages.
Bets are "raise TO" a total street contribution.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from bot.actions import Action, LegalActions, is_legal
from bot.cards import FULL_DECK
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, Info,
                          MatchEnd, MatchInfo, OppAction, ProtocolError, Showdown,
                          parse_action)
from bot.game.rules_spec import Rules, holdem_rules, to_rules
from bot.game.runner import LazyRng, act, advance, legal_actions
from bot.game.steps.cards import safe_action_for_hole
from bot.game.state import ALL, INFO_KINDS, GameState
from lab.players import PlayerCrashed, PlayerTimeout

SB, BB = 0, 1


class Forfeit(Exception):
    def __init__(self, role: int, reason: str) -> None:
        super().__init__(reason)
        self.role = role
        self.reason = reason


def deck_for(seed: int, hand_index: int, deck: Sequence[int] = FULL_DECK) -> list[int]:
    """Deterministic shuffled deck for one hand of one seed."""
    order = np.random.default_rng([seed, hand_index]).permutation(len(deck)).tolist()
    return [deck[i] for i in order]


@dataclass
class HandResult:
    deltas: list[int]               # chip result per role
    showdown: bool
    folded: Optional[int]           # role that folded, if any
    pot: int
    house: int = 0                  # chips that left the table (rake, burned bids)


class Seat:
    """Per-player bookkeeping the engine keeps across a match."""

    def __init__(self, player, bank_s: float, clock_scale: float = 1.0,
                 reply_limit_s: Optional[float] = None) -> None:
        self.player = player
        self.bank = bank_s
        self.clock_scale = clock_scale   # >1 simulates a slower machine: every reply is charged x
        self.reply_limit_s = reply_limit_s   # a single reply over this forfeits (None = no cap)
        self.errors = 0          # illegal / unparseable replies
        self.decisions = 0
        self.worst_decision_s = 0.0
        self.first_decision_s = 0.0      # includes process start-up overlap for subprocesses
        self.worst_after_first_s = 0.0


class Hand:
    """One hand: a thin driver around bot.game. The rules (steps, legality, payoffs) live
    in bot/game/; this class adds players, the time bank and the protocol messages.
    `seats[role]` gives the player for each role (0 = SB, 1 = BB)."""

    def __init__(self, variant, seats: Sequence[Seat], stacks: Sequence[int],
                 deck: list[int], hand_id: int, on_illegal: str = "fold",
                 rng=None, audit: bool = False) -> None:
        self.seats = list(seats)
        self.rules = to_rules(variant)                  # a VariantSpec or compiled Rules
        self.st = GameState(self.rules, deck, list(stacks), hand_id, audit=audit)
        self.announce_level = bool(getattr(self.rules, "has_schedule", False)
                                   or getattr(self.rules, "ante", 0))
        self.hand_id = hand_id
        self.on_illegal = on_illegal
        self.rng = rng
        self._flushed = 0

    # The game state's cards and chips, under the names the old engine used.
    hole = property(lambda self: self.st.hole)
    board = property(lambda self: self.st.board)
    deck = property(lambda self: self.st.deck)
    stack = property(lambda self: self.st.stack)
    start = property(lambda self: self.st.start)
    bet = property(lambda self: self.st.bet)
    total = property(lambda self: self.st.total)
    street = property(lambda self: self.st.street)
    folded = property(lambda self: self.st.folded)

    @property
    def pot(self) -> int:
        return self.st.pot

    # ---- messages
    def notify(self, role: int, msg) -> None:
        try:
            self.seats[role].player.notify(msg)
        except PlayerCrashed as e:
            raise Forfeit(role, f"crash: {e}") from None

    def broadcast(self, msg) -> None:
        for r in (SB, BB):
            self.notify(r, msg)

    def flush_events(self) -> None:
        """Turn new game events into protocol messages for the players who may see them."""
        events = self.st.events
        while self._flushed < len(events):
            e = events[self._flushed]
            self._flushed += 1
            k = e.kind
            viewers = (SB, BB) if e.visible == ALL else (e.visible,)
            if k == "hole":
                self.notify(e.visible, HoleCards(e.data["cards"]))
            elif k == "board":
                self.broadcast(BoardUpdate(e.data["street"], e.data["cards"], e.data.get("index")))
            elif k in ("action", "special"):
                for r in viewers:
                    if r != e.player:          # the actor already knows its own choice
                        self.notify(r, OppAction(e.data["action"]))
            elif k == "showdown":
                self.notify(e.visible, Showdown(e.data["cards"]))
            elif k in INFO_KINDS:
                for r in viewers:
                    who = "none" if e.player < 0 else ("me" if e.player == r else "opp")
                    value = e.data.get("value")
                    self.notify(r, Info(k, who, e.data.get("cards", ()),
                                        int(value) if value is not None else None))
            elif k == "end":
                self.notify(e.visible, HandEnd(e.data["delta"]))

    # ---- asking a player
    def ask(self, role: int, legal: LegalActions) -> Action:
        """Get a legal action from `role`, enforcing the time bank and illegal-reply policy."""
        seat, st = self.seats[role], self.st
        req = ActRequest(st.pot, st.to_call(role), st.stack[role], st.stack[1 - role], legal,
                         round(seat.bank, 4), st.bet[role], st.bet[1 - role])
        t0 = time.perf_counter()
        try:
            raw = seat.player.act(req)
        except PlayerTimeout:
            seat.bank = 0.0
            raise Forfeit(role, "timeout") from None
        except PlayerCrashed as e:
            raise Forfeit(role, f"crash: {e}") from None
        dt = (time.perf_counter() - t0) * seat.clock_scale
        seat.bank -= dt
        seat.decisions += 1
        seat.worst_decision_s = max(seat.worst_decision_s, dt)
        if seat.decisions == 1:
            seat.first_decision_s = dt
        else:
            seat.worst_after_first_s = max(seat.worst_after_first_s, dt)
        if seat.reply_limit_s is not None and dt > seat.reply_limit_s:
            raise Forfeit(role, f"reply took {dt:.2f}s > {seat.reply_limit_s:g}s")
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
            action = safe_action_for_hole(legal, st.hole[role])   # auto check/fold/discard
        return action

    # ---- whole hand
    def play(self) -> HandResult:
        st = self.st
        lv = st.level if self.announce_level and st.level else None
        for r in (SB, BB):
            self.notify(r, HandStart(self.hand_id, r, st.stack[r], st.stack[1 - r],
                                     round(self.seats[r].bank, 4),
                                     *((lv[0], lv[1], lv[2]) if lv else ())))
        while True:
            actor = advance(st, self.rng)
            self.flush_events()
            if actor is None:
                break
            action = self.ask(actor, legal_actions(st, actor))
            act(st, actor, action)
            self.flush_events()
        return HandResult(list(st.deltas), st.showdown, st.folded, st.pot, st.house)


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
    house: int = 0                                         # total rake / burned chips

    def score(self, index: int) -> float:
        """Match points for player `index`: win 1, draw 0.5, loss 0."""
        if self.forfeit is not None:
            return 0.0 if self.forfeit == index else 1.0
        c = self.chips[index]
        return 1.0 if c > 0 else (0.5 if c == 0 else 0.0)


def play_match(players: Sequence, cfg=None, seed: int = 0,
               hands: Optional[int] = None, on_illegal: str = "fold",
               time_bank_s: Optional[float] = None,
               audit: bool = False, clock_scale: float = 1.0,
               reply_limit_s: Optional[float] = None) -> MatchResult:
    """Play one match between players[0] and players[1]. Player (h % 2) is SB in hand h.
    `cfg` may be a VariantSpec or compiled Rules (default: Hold'em). audit=True checks every
    event's visibility and chip conservation in every hand (AssertionError on failure).
    clock_scale charges every reply that many times its real duration (a slower machine);
    reply_limit_s forfeits a single reply that takes longer (the real engine's 5 s rule)."""
    rules = holdem_rules() if cfg is None else to_rules(cfg)
    hands = rules.hands_per_match if hands is None else hands
    bank = rules.time_bank_s if time_bank_s is None else time_bank_s
    seats = [Seat(p, bank, clock_scale, reply_limit_s) for p in players]
    info = MatchInfo(hands, bank, rules.small_blind, rules.big_blind, rules.starting_stack)
    start = rules.starting_stack
    stacks = [start, start]
    chips = [0, 0]
    result = MatchResult(chips, 0, [0, 0])
    try:
        for i in (0, 1):
            set_rules = getattr(players[i], "set_rules", None)
            if set_rules is not None:
                set_rules(rules)          # in-process brains learn the variant directly
            _safe_notify(seats, i, info)
        for h in range(hands):
            if not rules.reset_stacks_each_hand and min(stacks) <= 0:
                if rules.bust_ends_match:
                    break                               # someone is bust: match over
                stacks = [s if s > 0 else start for s in stacks]   # rebuy (chips still count)
            sb_player = h % 2
            by_role = [seats[sb_player], seats[1 - sb_player]]
            role_stacks = ([start, start] if rules.reset_stacks_each_hand
                           else [stacks[sb_player], stacks[1 - sb_player]])
            hand = Hand(rules, by_role, role_stacks, deck_for(seed, h, rules.deck), h,
                        on_illegal, rng=LazyRng([seed, h, 1]), audit=audit)
            try:
                res = hand.play()
                if audit:
                    assert sum(res.deltas) + res.house == 0, \
                        f"hand {h}: chips not conserved {res.deltas} (house {res.house})"
            except Forfeit as f:
                result.forfeit = sb_player if f.role == SB else 1 - sb_player
                result.forfeit_reason = f.reason
                break
            d = [res.deltas[SB], res.deltas[BB]] if sb_player == 0 else [res.deltas[BB], res.deltas[SB]]
            for i in (0, 1):
                chips[i] += d[i]
                stacks[i] += d[i]
            result.hand_deltas.append(d[0])
            result.house += res.house
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
