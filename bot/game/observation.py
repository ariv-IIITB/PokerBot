"""What one player knows: built ONLY from events visible to that player.

`messages_for(e, p)` is the one rule for what player p receives for game event e: the lab
engine sends exactly these messages, and the bot's replay (bot/sim/replay.py) expects exactly
these, matched through `card_entry` (also what bot/state.py logs). `observe(st, p)` replays the
event log through p's eyes. Because nothing is read from the hidden parts of the state, a step
that emits an event with the wrong visibility shows up as a leak in tests (tests/test_game.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bot.game.state import ALL, INFO_KINDS, REVEAL_KINDS
from bot.protocol import BoardUpdate, HandEnd, HoleCards, Info, OppAction, Showdown


def messages_for(e, viewer: int) -> list:
    """The neutral protocol messages `viewer` receives for event `e` ([] = nothing)."""
    if e.visible != ALL and e.visible != viewer:
        return []
    k, d = e.kind, e.data
    if k == "hole":
        return [HoleCards(d["cards"])] if e.player == viewer else []
    if k == "board":
        return [BoardUpdate(d["street"], d["cards"], d.get("index"))]
    if k in ("action", "special"):
        return [OppAction(d["action"])] if e.player != viewer else []   # the actor knows
    if k == "showdown":
        return [Showdown(d["cards"])]
    if k in INFO_KINDS:
        who = "none" if e.player < 0 else ("me" if e.player == viewer else "opp")
        value = d.get("value")
        return [Info(k, who, d.get("cards", ()), int(value) if value is not None else None)]
    if k == "end":
        return [HandEnd(d["delta"])]
    return []


def card_entry(msg):
    """(kind, cards) for a message that shows cards, else None: how a hand is re-aligned."""
    if isinstance(msg, HoleCards):
        return ("hole", tuple(msg.cards))
    if isinstance(msg, BoardUpdate):
        return ("board", tuple(msg.cards))
    if isinstance(msg, Info) and msg.cards:
        return ("info:" + msg.kind, tuple(msg.cards))
    return None


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


def visible_events(st, p: int):
    return [e for e in st.events if e.visible == ALL or e.visible == p]


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
