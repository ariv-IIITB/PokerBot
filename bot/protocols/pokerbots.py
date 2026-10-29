"""The official Pokerbots 2026 wire format (docs/rules/protocol.pdf): JSON lines.

Bot side (what the submitted bot runs)
  parse_line    wire message -> neutral messages. The real protocol is *stateless on the wire*
                for opponent actions: they arrive only inside `history`, so this adapter keeps
                per-hand state (our hole cards, the board, how much history it has already
                turned into messages) and emits, in the order the lab engine would have sent them:
                  new_hand         HandStart, HoleCards
                  action_request   [BoardUpdate] OppAction... [BoardUpdate] ActRequest
                  discard_request  [OppAction (inferred: the flop closer)] [BoardUpdate] ActRequest
                  discard_result   the engine's discard messages, in the engine's per-seat order
                  hand_result      missing OppActions, BoardUpdates, Showdown, HandEnd
  encode_action  Action -> {"type":"action",...} / {"type":"discard","card":...}

Engine side (the lab's SubprocessPlayer: any bot that speaks this protocol can be seated)
  encode_message  neutral messages -> wire lines (buffering HandStart+HoleCards into new_hand,
                  keeping a history from OppAction messages and our own parsed replies)
  parse_action    reply line -> Action (a discard card becomes its hole-card index)

Conventions: neutral hand ids are 0-based, the wire's are 1-based. Seat 0 = "button". Street
numbers are the lab engine's (1 flop, 2 turn, 3 river). The opponent's discard arrives as the
card itself, never as an index into their hidden hand, so OppAction(special) carries the
placeholder index "0": the replay maps the revealed card onto whichever hidden slot that is.
"""
from __future__ import annotations

import json
from typing import Optional

from bot.actions import (CALL, CHECK, FOLD, RAISE, SPECIAL, Action, LegalActions,
                         SpecialOption, is_legal)
from bot.cards import format_card, parse_card
from bot.game.steps.cards import fallback_discard, safe_action_for_hole
from bot.log import warn
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, Info,
                          MatchEnd, MatchInfo, Message, OppAction, ProtocolError, Showdown)
from bot.protocols.base import Adapter

PROTOCOL_VERSION = "1.0"
STREETS = ("preflop", "flop", "turn", "river")
STREET_OF_BOARD_LEN = {3: 1, 4: 2, 5: 3}                 # board cards -> street number
BOARD_LEN = {1: 3, 2: 4, 3: 5}
ACTION_NAMES = {FOLD: "fold", CHECK: "check", CALL: "call", RAISE: "raise"}
NAME_ACTIONS = {v: k for k, v in ACTION_NAMES.items()}
MAX_RAISES = 4                                           # per street; preflop the BB is the first
PER_RESPONSE_MS = 5000
HIDDEN_INDEX = "0"                                       # placeholder for the opponent's slot


def _compact(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _int(msg: dict, key: str) -> int:
    v = msg[key]
    if isinstance(v, bool) or not isinstance(v, int):
        raise ProtocolError(f"{key} must be an integer, got {v!r}")
    return v


def _opt_ms(msg: dict, key: str) -> Optional[float]:
    """An optional millisecond field as seconds (None when absent or not a number)."""
    v = msg.get(key)
    return v / 1000.0 if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _cards(msg: dict, key: str) -> tuple[int, ...]:
    v = msg[key]
    if not isinstance(v, list):
        raise ProtocolError(f"{key} must be a list of cards")
    return tuple(parse_card(c) for c in v)


def _fmt(cards) -> list[str]:
    return [format_card(c) for c in cards]


class PokerbotsAdapter(Adapter):
    name = "pokerbots"
    hides_opponent_choice = True

    def __init__(self) -> None:
        self.per_response_s: Optional[float] = None
        self._new_match()

    def _new_match(self) -> None:
        # bot side
        self.hole: list[int] = []
        self.board: tuple[int, ...] = ()
        self.seat = 0
        self.sidx = 0                       # street number of the last board we emitted
        self.consumed = 0                   # history entries already turned into messages
        self.sent: list[tuple] = []         # our replies this hand: (kind, amount)
        self.sent_seen = 0                  # how many of them history has echoed back
        self.last_known: Optional[tuple[str, str, int]] = None   # (actor, action, street) of the last action
        self.inferred: list[tuple[int, str]] = []   # opponent actions we emitted before history listed them
        self.my_bet = self.opp_bet = 0      # this street's totals as far as we know
        self.bet_street = 0
        # engine side
        self.sb, self.bb = 1, 2
        self.e_pending: Optional[dict] = None               # new_hand waiting for HoleCards
        self.e_hand_id = 0
        self.e_seat = 0
        self.e_hole: list[int] = []
        self.e_board: list[int] = []
        self.e_sidx = 0
        self.e_history: list[dict] = []
        self.e_bets = [0, 0]                # [mine, opponent's] on the current street
        self.e_discards: dict = {}
        self.e_opp_discard: Optional[int] = None
        self.e_opp_hole: Optional[tuple] = None
        self.e_req: Optional[ActRequest] = None

    # ------------------------------------------------------------------ bot side: wire -> neutral

    def parse_line(self, line: str):
        line = line.strip()
        if not line:
            return None
        try:
            msg = json.loads(line)
        except ValueError as e:
            raise ProtocolError(f"not JSON: {e}") from None
        if not isinstance(msg, dict):
            raise ProtocolError("a message must be a JSON object")
        handler = self._handlers().get(msg.get("type"))
        if handler is None:
            return None                                   # unknown type: ignore
        try:
            return handler(msg)
        except ProtocolError:
            raise
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
            raise ProtocolError(f"bad {msg['type']} message: {e!r}") from None

    def _handlers(self) -> dict:
        return {"init": self._on_init, "new_hand": self._on_new_hand,
                "action_request": self._on_action_request,
                "discard_request": self._on_discard_request,
                "discard_result": self._on_discard_result, "hand_result": self._on_hand_result,
                "notice": self._on_notice, "match_end": self._on_match_end}

    def _on_init(self, m: dict):
        self._new_match()
        if "per_response_ms" in m:
            self.per_response_s = _int(m, "per_response_ms") / 1000.0
        return MatchInfo(hands=_int(m, "total_hands"), timebank=_int(m, "time_bank_ms") / 1000.0,
                         sb=_int(m, "small_blind"), bb=_int(m, "big_blind"),
                         stack=_int(m, "starting_stack"))

    def _on_new_hand(self, m: dict):
        seat = {"button": 0, "big_blind": 1}[m["seat"]]
        hole = _cards(m, "hole_cards")
        self.hole, self.board, self.seat = list(hole), (), seat
        self.sidx = self.consumed = self.sent_seen = 0
        self.sent, self.last_known, self.inferred = [], None, []
        self.my_bet = self.opp_bet = self.bet_street = 0
        return [HandStart(_int(m, "hand_id") - 1, seat, _int(m, "stack"), _int(m, "opp_stack")),
                HoleCards(hole)]

    def _catch_up(self, history: list, board: tuple) -> list[Message]:
        """Messages for history entries we have not turned into messages yet."""
        out: list[Message] = []
        for entry in history[self.consumed:]:
            if not isinstance(entry, dict):
                raise ProtocolError("history entries must be objects")
            street = STREETS.index(entry["street"])
            if street > self.sidx:
                n = BOARD_LEN.get(street)
                if n is not None and len(board) >= n:
                    self.board, self.sidx = board[:n], street
                    out.append(BoardUpdate(street, self.board))
            name, actor = entry["action"], entry["actor"]
            kind = NAME_ACTIONS.get(name)
            if kind is None:                              # not a voluntary action: skip
                continue
            amount = _int(entry, "amount") if name in ("call", "raise") else None
            self.last_known = (actor, name, street)
            if actor == "me":
                self._check_own(name, amount)
            elif actor == "opp":
                if self.inferred and self.inferred[0] == (street, name):
                    self.inferred.pop(0)                  # already emitted at the discard request
                    continue
                out.append(OppAction(Action.raise_to(amount) if kind == RAISE else Action(kind)))
            else:
                raise ProtocolError(f"unknown actor {actor!r}")
        self.consumed = max(self.consumed, len(history))
        return out

    def _check_own(self, name: str, amount: Optional[int]) -> None:
        """Our own entries are not replayed (we recorded them when we sent them): just verify."""
        if self.sent_seen < len(self.sent):
            kind, sent_amount = self.sent[self.sent_seen]
            if ACTION_NAMES.get(kind) != name or (kind == RAISE and sent_amount != amount):
                warn(f"history says we did {name} {amount}, but we sent {kind} {sent_amount}")
        self.sent_seen += 1

    def _catch_up_board(self, board: tuple) -> list[Message]:
        n = len(board)
        if n > len(self.board) and n in STREET_OF_BOARD_LEN:
            self.board, self.sidx = board, STREET_OF_BOARD_LEN[n]
            return [BoardUpdate(self.sidx, board)]
        return []

    def _on_action_request(self, m: dict):
        board = _cards(m, "board")
        out = self._catch_up(m["history"], board)
        out += self._catch_up_board(board)
        names = m["legal_actions"]
        if not isinstance(names, list):
            raise ProtocolError("legal_actions must be a list")
        rmin = _int(m, "min_raise") if "raise" in names else None
        rmax = _int(m, "max_raise") if "raise" in names else None
        legal = LegalActions(fold="fold" in names, check="check" in names, call="call" in names,
                             raise_min=rmin, raise_max=rmax)
        self.my_bet, self.opp_bet, self.bet_street = _int(m, "my_bet"), _int(m, "opp_bet"), self.sidx
        out.append(ActRequest(_int(m, "pot"), _int(m, "to_call"), _int(m, "my_stack"),
                              _int(m, "opp_stack"), legal, _opt_ms(m, "time_left_ms"),
                              self.my_bet, self.opp_bet))
        return out

    def _on_discard_request(self, m: dict):
        self.hole = list(_cards(m, "hole_cards"))
        board = _cards(m, "board")
        out: list[Message] = []
        # The opponent's answer to our last action is not listed anywhere yet. Betting ended
        # without a fold, so they called our bet or raise (which may have been preflop, if all
        # chips went in) or, on the flop, checked behind our check (the big blind acts first
        # there; the button's check is what closes the round). The engine sent this action
        # before the flop, so it goes first.
        if self.last_known is not None and self.last_known[0] == "me":
            _, name, street = self.last_known
            if name == "raise":
                out.append(OppAction(Action.call()))
                self.inferred.append((street, "call"))
            elif name == "check" and street == 1 and self.seat == 1:   # the button's check closes it
                out.append(OppAction(Action.check()))
                self.inferred.append((street, "check"))
        out += self._catch_up_board(board)
        common = self.my_bet if self.bet_street == self.sidx == 1 else 0
        tokens = tuple(str(i) for i in range(len(self.hole)))
        legal = LegalActions(special=SpecialOption("discard", tokens))
        out.append(ActRequest(_int(m, "pot"), 0, _int(m, "my_stack"), _int(m, "opp_stack"), legal,
                              _opt_ms(m, "time_left_ms"), common, common))
        return out

    def _on_discard_result(self, m: dict):
        mine, theirs = parse_card(m["my_discard"]), parse_card(m["opp_discard"])
        self.hole = list(_cards(m, "hole_cards"))
        hole = HoleCards(tuple(self.hole))
        me, opp = Info("reveal", "me", (mine,)), Info("reveal", "opp", (theirs,))
        chose = OppAction(Action.special(HIDDEN_INDEX))
        # The engine applies the button's discard first: each seat hears it in this order.
        return [hole, me, chose, opp] if self.seat == 0 else [chose, opp, hole, me]

    def _on_hand_result(self, m: dict):
        board = _cards(m, "board")
        out = self._catch_up(m["history"], board)
        for n in (3, 4, 5):
            if len(self.board) < n <= len(board):
                self.board, self.sidx = board[:n], STREET_OF_BOARD_LEN[n]
                out.append(BoardUpdate(self.sidx, self.board))
        shown = m.get("opp_hole_cards")
        if m.get("result") == "showdown" and shown:
            out.append(Showdown(tuple(parse_card(c) for c in shown)))
        out.append(HandEnd(_int(m, "net")))
        return out

    def _on_notice(self, m: dict):
        warn(f"engine notice: {m.get('code')} applied={m.get('applied')}")
        return None

    def _on_match_end(self, m: dict):
        return MatchEnd()

    # ------------------------------------------------------------------ bot side: action -> wire

    def encode_action(self, action: Action) -> str:
        kind = action.kind
        if kind == SPECIAL:                               # a discard: not part of `history`
            try:
                card = self.hole[int(action.choice)]
            except (TypeError, ValueError, IndexError):   # cannot happen for a legal choice
                card = fallback_discard(self.hole) if self.hole else parse_card("2c")
            return _compact({"type": "discard", "card": format_card(card)})
        if kind == RAISE:
            self._note_own(kind, action.amount)
            return _compact({"type": "action", "action": "raise", "amount": int(action.amount)})
        self._note_own(kind, None)
        return _compact({"type": "action", "action": ACTION_NAMES[kind]})

    def _note_own(self, kind: str, amount: Optional[int]) -> None:
        self.sent.append((kind, amount))
        self.last_known = ("me", ACTION_NAMES[kind], self.sidx)
        if kind == RAISE:
            self.my_bet = int(amount)
        elif kind == CALL:
            self.my_bet = self.opp_bet

    def recover(self, line: str) -> Optional[str]:
        """A request we could not parse is still a request: the engine is waiting, and a missing
        reply forfeits the match. A blind check is safe (an illegal action is corrected to check
        if legal, else fold); a discard names our lowest card. Anything else gets no reply."""
        if '"discard_request"' in line:
            card = fallback_discard(self.hole) if self.hole else parse_card("2c")
            return _compact({"type": "discard", "card": format_card(card)})
        if '"action_request"' in line:
            return _compact({"type": "action", "action": "check"})
        return None

    # ------------------------------------------------------------------ engine side: neutral -> wire

    def encode_message(self, msg: Message):
        if isinstance(msg, MatchInfo):
            self.sb, self.bb = msg.sb, msg.bb
            return _compact({"type": "init", "protocol_version": PROTOCOL_VERSION,
                             "total_hands": msg.hands, "starting_stack": msg.stack,
                             "small_blind": msg.sb, "big_blind": msg.bb,
                             "time_bank_ms": int(round(msg.timebank * 1000)),
                             "per_response_ms": PER_RESPONSE_MS})
        if isinstance(msg, HandStart):
            self.e_hand_id, self.e_seat = msg.hand_id, msg.seat
            self.e_pending = {"hand_id": msg.hand_id + 1,
                              "seat": "button" if msg.seat == 0 else "big_blind",
                              "stack": msg.stack, "opp_stack": msg.oppstack}
            self.e_hole, self.e_board, self.e_sidx = [], [], 0
            self.e_history, self.e_discards = [], {}
            self.e_opp_discard = self.e_opp_hole = self.e_req = None
            self.e_bets = [self.sb, self.bb] if msg.seat == 0 else [self.bb, self.sb]
            return ""
        if isinstance(msg, HoleCards):
            self.e_hole = list(msg.cards)
            if self.e_pending is not None:
                line = {"type": "new_hand", **{k: self.e_pending[k] for k in ("hand_id", "seat")},
                        "hole_cards": _fmt(msg.cards), "stack": self.e_pending["stack"],
                        "opp_stack": self.e_pending["opp_stack"]}
                self.e_pending = None
                return _compact(line)
            return ""                                    # after the discard: sent in discard_result
        if isinstance(msg, BoardUpdate):
            self.e_board, self.e_sidx, self.e_bets = list(msg.cards), msg.street, [0, 0]
            return ""
        if isinstance(msg, OppAction):
            self._engine_note("opp", msg.action)
            return ""
        if isinstance(msg, ActRequest):
            return self._engine_request(msg)
        if isinstance(msg, Info):
            return self._engine_info(msg)
        if isinstance(msg, Showdown):
            self.e_opp_hole = tuple(msg.oppcards)
            return ""
        if isinstance(msg, HandEnd):
            return _compact({
                "type": "hand_result", "hand_id": self.e_hand_id + 1,
                "result": "showdown" if self.e_opp_hole else "fold", "net": msg.delta,
                "board": _fmt(self.e_board), "my_hole_cards": _fmt(self.e_hole),
                "opp_hole_cards": _fmt(self.e_opp_hole) if self.e_opp_hole else None,
                "opp_discard": format_card(self.e_opp_discard)
                if self.e_opp_discard is not None else None,
                "history": list(self.e_history)})
        if isinstance(msg, MatchEnd):
            return _compact({"type": "match_end", "reason": "complete"})
        return ""

    def _engine_note(self, actor: str, action: Action) -> None:
        """Add a voluntary action to the hand history (discards are not history)."""
        if action.kind == SPECIAL:
            return
        me = 0 if actor == "me" else 1
        entry = {"street": STREETS[min(self.e_sidx, 3)], "actor": actor,
                 "action": ACTION_NAMES[action.kind]}
        if action.kind == RAISE:
            self.e_bets[me] = int(action.amount)
            entry["amount"] = int(action.amount)
        elif action.kind == CALL:
            self.e_bets[me] = self.e_bets[1 - me]
            entry["amount"] = self.e_bets[me]
        self.e_history.append(entry)

    def _engine_request(self, req: ActRequest) -> str:
        self.e_req = req
        if req.mybet is not None:
            self.e_bets = [req.mybet, req.oppbet if req.oppbet is not None else self.e_bets[1]]
        if req.legal.can_special:
            return _compact({"type": "discard_request", "hand_id": self.e_hand_id + 1,
                             "hole_cards": _fmt(self.e_hole), "board": _fmt(self.e_board),
                             "pot": req.pot, "my_stack": req.mystack, "opp_stack": req.oppstack,
                             "time_left_ms": int(round((req.timeleft or 0) * 1000))})
        legal = req.legal
        names = [n for n, ok in (("fold", legal.fold), ("check", legal.check),
                                 ("call", legal.call), ("raise", legal.can_raise)) if ok]
        street = STREETS[min(self.e_sidx, 3)]
        used = sum(1 for e in self.e_history if e["street"] == street and e["action"] == "raise")
        used += 1 if self.e_sidx == 0 else 0                      # the big blind
        line = {"type": "action_request", "hand_id": self.e_hand_id + 1, "street": street,
                "board": _fmt(self.e_board), "pot": req.pot, "my_bet": self.e_bets[0],
                "opp_bet": self.e_bets[1], "to_call": req.tocall, "my_stack": req.mystack,
                "opp_stack": req.oppstack, "legal_actions": names}
        if legal.can_raise:
            line.update(min_raise=legal.raise_min, max_raise=legal.raise_max)
        line.update(raises_left=max(0, MAX_RAISES - used), history=list(self.e_history),
                    time_left_ms=int(round((req.timeleft or 0) * 1000)))
        return _compact(line)

    def _engine_info(self, info: Info) -> str:
        if info.kind != "reveal" or not info.cards:
            return ""
        self.e_discards[info.who] = info.cards[0]
        if info.who == "opp":
            self.e_opp_discard = info.cards[0]
        if "me" in self.e_discards and "opp" in self.e_discards:
            line = {"type": "discard_result", "hand_id": self.e_hand_id + 1,
                    "my_discard": format_card(self.e_discards["me"]),
                    "opp_discard": format_card(self.e_discards["opp"]),
                    "hole_cards": _fmt(self.e_hole)}
            self.e_discards = {}
            return _compact(line)
        return ""

    def parse_action(self, line: str) -> Action:
        """The engine's reading of a reply. Whatever the bot says, the history records what the
        engine will apply: the action if legal, else the engine's correction."""
        req = self.e_req
        try:
            action = self._decode_reply(line)
        except (ValueError, KeyError, TypeError, ProtocolError) as e:
            self._engine_record_correction(req)
            raise ProtocolError(f"bad reply {line[:60]!r}: {e!r}") from None
        if req is not None and not is_legal(action, req.legal):
            self._engine_record_correction(req)
        else:
            self._engine_note("me", action)
        return action

    def _decode_reply(self, line: str) -> Action:
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ProtocolError("not an object")
        kind = obj.get("type")
        if kind == "discard":
            card = parse_card(obj["card"])
            if card not in self.e_hole:
                raise ProtocolError("discard is not one of the hole cards")
            return Action.special(str(self.e_hole.index(card)))
        if kind != "action" or obj.get("action") not in NAME_ACTIONS:
            raise ProtocolError("unknown reply")
        if obj["action"] == "raise":
            amount = obj.get("amount")
            if isinstance(amount, bool) or not isinstance(amount, int):
                raise ProtocolError("raise needs an integer amount")
            return Action.raise_to(amount)
        return Action(NAME_ACTIONS[obj["action"]])

    def _engine_record_correction(self, req: Optional[ActRequest]) -> None:
        if req is not None:
            self._engine_note("me", safe_action_for_hole(req.legal, self.e_hole))
