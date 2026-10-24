"""Hand and match state, built purely from neutral protocol messages.

Brains read `GameState` (never raw text). The main loop feeds every parsed message to
`GameState.apply` and records our own replies with `record_my_action`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from bot.actions import Action
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, Info,
                          MatchEnd, MatchInfo, Message, OppAction, Showdown)

ME = "me"
OPP = "opp"


@dataclass(frozen=True)
class ActionRecord:
    street: int
    actor: str          # ME or OPP
    action: Action


@dataclass
class HandState:
    hand_id: int
    seat: int                       # 0 = small blind / button (placeholder convention)
    start_stack: int
    opp_start_stack: int
    hole: tuple[int, ...] = ()
    board: tuple[int, ...] = ()
    street: int = 0                 # 0 = preflop; index into GameConfig.streets
    pot: int = 0
    tocall: int = 0
    my_stack: int = 0
    opp_stack: int = 0
    my_bet: Optional[int] = None     # chips in on this street (if the engine says)
    opp_bet: Optional[int] = None
    history: list[ActionRecord] = field(default_factory=list)
    opp_cards: tuple[int, ...] = ()  # filled at showdown
    info: list[Info] = field(default_factory=list)     # INFO messages this hand
    boards: dict = field(default_factory=dict)          # several boards: index -> cards
    card_log: list = field(default_factory=list)        # (kind, cards) of every card message,
                                                        # in order: used to rebuild the hand
    sb: Optional[int] = None        # this hand's blinds if the engine announced them
    bb: Optional[int] = None
    ante: Optional[int] = None
    offer: tuple[int, ...] = ()      # cards currently offered to me (choose steps)
    delta: Optional[int] = None      # our chip result, set at END
    finished: bool = False

    @property
    def known_opp_cards(self) -> set[int]:
        """Opponent cards I've been shown (exposed / peeked / revealed), still possibly held."""
        return {c for i in self.info if i.who == "opp" and i.kind in ("expose", "peek", "reveal")
                for c in i.cards}

    @property
    def dead_cards(self) -> set[int]:
        """Cards I know are out of play (burned / revealed discards / peeked deck cards)."""
        return {c for i in self.info if i.kind in ("burn", "reveal") or
                (i.kind == "peek" and i.who == "none") for c in i.cards}

    def actions_on(self, street: int, actor: Optional[str] = None) -> list[Action]:
        """Actions taken on a street, optionally only by one actor."""
        return [r.action for r in self.history
                if r.street == street and (actor is None or r.actor == actor)]


@dataclass
class GameState:
    match: MatchInfo = field(default_factory=MatchInfo)  # defaults until MATCH arrives
    hand: Optional[HandState] = None
    hands_played: int = 0           # completed hands
    bankroll: int = 0               # cumulative chip result this match
    timeleft: Optional[float] = None  # latest engine-reported bank
    match_over: bool = False

    @property
    def hands_remaining(self) -> int:
        """Hands still to play, counting the current one if it hasn't ended."""
        return max(0, self.match.hands - self.hands_played)

    def apply(self, msg: Message) -> None:
        """Update state from one engine message."""
        if isinstance(msg, MatchInfo):
            self.match = msg
        elif isinstance(msg, HandStart):
            self.hand = HandState(msg.hand_id, msg.seat, msg.stack, msg.oppstack,
                                  my_stack=msg.stack, opp_stack=msg.oppstack,
                                  sb=msg.sb, bb=msg.bb, ante=msg.ante)
            self._set_time(msg.timeleft)
        elif isinstance(msg, MatchEnd):
            self.match_over = True
        elif self.hand is None:
            return  # hand-level message outside a hand: ignore
        elif isinstance(msg, HoleCards):
            self.hand.hole = msg.cards
            self.hand.card_log.append(("hole", msg.cards))
        elif isinstance(msg, BoardUpdate):
            self.hand.card_log.append(("board", msg.cards))
            if msg.index is not None:
                self.hand.boards[msg.index] = msg.cards
                if msg.index == 0:
                    self.hand.board = msg.cards
            else:
                self.hand.board = msg.cards
            self.hand.street = msg.street
        elif isinstance(msg, OppAction):
            self.hand.history.append(ActionRecord(self.hand.street, OPP, msg.action))
        elif isinstance(msg, ActRequest):
            h = self.hand
            h.pot, h.tocall, h.my_stack, h.opp_stack = msg.pot, msg.tocall, msg.mystack, msg.oppstack
            h.my_bet, h.opp_bet = msg.mybet, msg.oppbet
            self._set_time(msg.timeleft)
        elif isinstance(msg, Showdown):
            self.hand.opp_cards = msg.oppcards
        elif isinstance(msg, Info):
            self.hand.info.append(msg)
            if msg.cards:
                self.hand.card_log.append(("info:" + msg.kind, msg.cards))
            if msg.kind == "offer":
                self.hand.offer = msg.cards
        elif isinstance(msg, HandEnd):
            if not self.hand.finished:
                self.hand.delta = msg.delta
                self.hand.finished = True
                self.bankroll += msg.delta
                self.hands_played += 1

    def record_my_action(self, action: Action) -> None:
        if self.hand is not None:
            self.hand.history.append(ActionRecord(self.hand.street, ME, action))

    def _set_time(self, t: Optional[float]) -> None:
        if t is not None:
            self.timeleft = t
