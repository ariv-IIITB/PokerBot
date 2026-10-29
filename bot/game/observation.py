"""What one player knows: built ONLY from events visible to that player.

This module is the single owner of event visibility:
  sees(e, p)         may player p see event e
  message_for(e, p)  the neutral protocol message p receives for e (None = nothing). The lab
                     engine sends exactly these; the bot's replay (bot/sim/replay.py) re-derives
                     them from a simulated hand to match its placeholders to real cards.
  card_entry(msg)    the (kind, cards) entry a card-carrying message adds to the bot's card
                     log (bot/state.py), in the same form for real and replayed messages.

Hidden choices: when a protocol does not tell us which of the opponent's hole cards they
discarded (bot/protocols/pokerbots.py: simultaneous discard), the choice arrives as slot
HIDDEN_CHOICE ("0") and the card itself as an INFO reveal. That is exact, not a guess: before
the reveal the opponent's hole cards are interchangeable placeholders in the replay, so
discarding slot 0 and mapping its placeholder to the revealed card is the same hand.

`observe(st, p)` replays the event log through p's eyes. Because nothing is read from
the hidden parts of the state, a step that emits an event with the wrong visibility shows
up as a leak in tests (see tests/test_game.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from bot.game.state import ALL, INFO_KINDS, REVEAL_KINDS
from bot.protocol import (BoardUpdate, HandEnd, HoleCards, Info, Message, OppAction,
                          Showdown)

HIDDEN_CHOICE = "0"          # the opponent's hidden discard slot (see the module docstring)


@dataclass
class View:
    player: int
    hole: tuple[int, ...] = ()                  # my current hole cards
    board: tuple[int, ...] = ()
    street: int = 0
    actions: list = field(default_factory=list)          # (player, Action) public actions
    revealed: dict = field(default_factory=dict)         # player -> cards shown to me
    seen_cards: set = field(default_factory=set)         # every card I have ever seen
    delta: int | None = None
    events: int = 0                                      # number of events I saw


def sees(e, p: int) -> bool:
    return e.visible == ALL or e.visible == p


def visible_events(st, p: int):
    return [e for e in st.events if sees(e, p)]


def message_for(e, p: int) -> Optional[Message]:
    """The message player p receives for event e, or None."""
    if not sees(e, p):
        return None
    k = e.kind
    if k == "hole":
        return HoleCards(e.data["cards"]) if e.player == p else None
    if k == "board":
        return BoardUpdate(e.data["street"], e.data["cards"], e.data.get("index"))
    if k in ("action", "special"):
        return OppAction(e.data["action"]) if e.player != p else None   # the actor knows it
    if k == "showdown":
        return Showdown(e.data["cards"])
    if k in INFO_KINDS:
        who = "none" if e.player < 0 else ("me" if e.player == p else "opp")
        value = e.data.get("value")
        return Info(k, who, e.data.get("cards", ()), int(value) if value is not None else None)
    if k == "end":
        return HandEnd(e.data["delta"])
    return None


def card_entry(msg: Message) -> Optional[tuple[str, tuple]]:
    """(kind, cards) for a message that shows cards, else None."""
    if isinstance(msg, HoleCards):
        return ("hole", tuple(msg.cards))
    if isinstance(msg, BoardUpdate):
        return ("board", tuple(msg.cards))
    if isinstance(msg, Info) and msg.cards:
        return ("info:" + msg.kind, tuple(msg.cards))
    return None


def observe(st, p: int) -> View:
    v = View(p)
    for e in visible_events(st, p):
        v.events += 1
        cards = e.data.get("cards", ())
        v.seen_cards.update(cards)
        if e.kind == "hole" and e.player == p:
            v.hole = tuple(cards)
        elif e.kind == "board":
            v.board = tuple(cards)
            v.street = e.data.get("street", v.street)
        elif e.kind in ("action", "special"):
            v.actions.append((e.player, e.data["action"]))
        elif e.kind in ("showdown", "expose", "reveal", "peek"):
            v.revealed[e.player] = v.revealed.get(e.player, ()) + tuple(cards)
        elif e.kind == "end":
            v.delta = e.data["delta"]
    return v


def legit_knowledge(st, p: int) -> set[int]:
    """Cards p may legitimately know even if they're now hidden: anything shown by a
    reveal-type event or on the public board, plus every card p itself has held or been
    offered (a card p gave away, or that left the board, is still known to p).
    Whether each event was allowed when it was emitted is checked by the state audit."""
    known = set()
    for e in visible_events(st, p):
        if (e.kind in REVEAL_KINDS or e.kind in ("board", "burn")
                or (e.kind in ("hole", "offer") and e.player == p)):
            known.update(e.data.get("cards", ()))
    return known


def hidden_from(st, p: int) -> set[int]:
    """Cards p must not know right now: undealt cards and other players' hole cards,
    minus what p legitimately learned."""
    hidden = set(st.deck)
    for q in range(st.n_players):
        if q != p:
            hidden |= set(st.hole[q])
    return hidden - legit_knowledge(st, p)
