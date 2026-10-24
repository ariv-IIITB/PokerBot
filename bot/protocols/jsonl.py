"""Mock protocol #1: JSON lines (one JSON object per line).

Engine -> bot, e.g.
  {"type": "match", "hands": 400, "timebank": 60.0, "sb": 1, "bb": 2, "stack": 400}
  {"type": "hand", "id": 3, "seat": 0, "stack": 400, "oppstack": 400, "timeleft": 59.2}
  {"type": "hole", "cards": ["Ah", "Kd"]}
  {"type": "board", "street": 1, "cards": ["Ts", "9h", "2c"]}
  {"type": "opp", "action": {"kind": "raise", "to": 6}}
  {"type": "act", "pot": 9, "tocall": 4, "mystack": 398, "oppstack": 394,
   "legal": {"fold": true, "call": true, "raise": [8, 400]}, "timeleft": 55.2}
  {"type": "show", "cards": [...]}   {"type": "info", "kind": "expose", ...}
  {"type": "end", "delta": -6}       {"type": "endmatch"}
Bot -> engine: {"kind": "fold"} | {"kind": "check"} | {"kind": "call"} |
               {"kind": "raise", "to": 8} | {"kind": "special", "choice": "0"}
Raise amounts are "raise TO" (same as the placeholder). Unknown types are ignored.
"""
from __future__ import annotations

import json
from dataclasses import fields

from bot.actions import (CALL, CHECK, FOLD, RAISE, SPECIAL, Action, LegalActions,
                         SpecialOption)
from bot.cards import format_card, parse_card
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, Info,
                          MatchEnd, MatchInfo, OppAction, ProtocolError, Showdown)
from bot.protocols.base import Adapter

KIND_NAMES = {FOLD: "fold", CHECK: "check", CALL: "call", RAISE: "raise", SPECIAL: "special"}
NAME_KINDS = {v: k for k, v in KIND_NAMES.items()}
TYPES = {MatchInfo: "match", HandStart: "hand", HoleCards: "hole", BoardUpdate: "board",
         OppAction: "opp", ActRequest: "act", Showdown: "show", Info: "info",
         HandEnd: "end", MatchEnd: "endmatch"}
BY_TYPE = {v: k for k, v in TYPES.items()}
CARD_FIELDS = {"cards", "oppcards"}


def _action_obj(a: Action) -> dict:
    d: dict = {"kind": KIND_NAMES[a.kind]}
    if a.kind == RAISE:
        d["to"] = a.amount
    if a.kind == SPECIAL:
        d["choice"] = a.choice
    return d


def _action_from(d) -> Action:
    if not isinstance(d, dict) or d.get("kind") not in NAME_KINDS:
        raise ProtocolError(f"bad action {d!r}")
    k = NAME_KINDS[d["kind"]]
    if k == RAISE:
        if not isinstance(d.get("to"), int) or isinstance(d.get("to"), bool):
            raise ProtocolError(f"bad raise {d!r}")
        return Action.raise_to(d["to"])
    if k == SPECIAL:
        if not isinstance(d.get("choice"), str):
            raise ProtocolError(f"bad special {d!r}")
        return Action.special(d["choice"])
    return Action(k)


def _legal_obj(L: LegalActions) -> dict:
    d: dict = {}
    for k in ("fold", "check", "call"):
        if getattr(L, k):
            d[k] = True
    if L.raise_min is not None and L.raise_max is not None:
        d["raise"] = [L.raise_min, L.raise_max]
        if L.raise_sizes:
            d["raise_sizes"] = list(L.raise_sizes)
        if L.raise_step:
            d["raise_step"] = L.raise_step
    if L.special is not None:
        sp = L.special
        d["special"] = ({"name": sp.name, "lo": sp.lo, "hi": sp.hi} if sp.is_range
                        else {"name": sp.name, "choices": list(sp.choices)})
    return d


def _legal_from(d: dict) -> LegalActions:
    if not isinstance(d, dict):
        raise ProtocolError("bad legal set")
    rmin = rmax = None
    if "raise" in d:
        rmin, rmax = (int(x) for x in d["raise"])
    special = None
    if "special" in d:
        s = d["special"]
        special = (SpecialOption(s["name"], (), int(s["lo"]), int(s["hi"])) if "lo" in s
                   else SpecialOption(s["name"], tuple(s["choices"])))
    sizes = tuple(d["raise_sizes"]) if d.get("raise_sizes") else None
    return LegalActions(bool(d.get("fold")), bool(d.get("check")), bool(d.get("call")),
                        rmin, rmax, special, sizes, d.get("raise_step"))


class JsonLinesAdapter(Adapter):
    name = "json"

    # ---- engine side
    def encode_message(self, msg) -> str:
        d: dict = {"type": TYPES[type(msg)]}
        for f in fields(msg):
            v = getattr(msg, f.name)
            if v is None:
                continue
            if f.name in CARD_FIELDS:
                v = [format_card(c) for c in v]
            elif f.name == "action":
                v = _action_obj(v)
            elif f.name == "legal":
                v = _legal_obj(v)
            d[f.name] = v
        return json.dumps(d, separators=(",", ":"))

    def parse_action(self, line: str) -> Action:
        try:
            return _action_from(json.loads(line))
        except (ValueError, TypeError) as e:
            raise ProtocolError(f"bad reply {line!r}: {e}") from None

    # ---- bot side
    def parse_line(self, line: str):
        line = line.strip()
        if not line:
            return None
        try:
            d = json.loads(line)
        except ValueError:
            raise ProtocolError(f"not JSON: {line[:40]!r}") from None
        if not isinstance(d, dict):
            raise ProtocolError("not a JSON object")
        cls = BY_TYPE.get(d.pop("type", None))
        if cls is None:
            return None                                     # unknown message type
        kw = {}
        try:
            names = {f.name for f in fields(cls)}
            for k, v in d.items():
                if k not in names:
                    continue                                # unknown key: ignore
                if k in CARD_FIELDS:
                    v = tuple(parse_card(c) for c in v)
                elif k == "action":
                    v = _action_from(v)
                elif k == "legal":
                    v = _legal_from(v)
                kw[k] = v
            return cls(**kw)
        except (TypeError, ValueError, KeyError) as e:
            raise ProtocolError(f"bad {cls.__name__}: {e}") from None

    def encode_action(self, action: Action) -> str:
        return json.dumps(_action_obj(action), separators=(",", ":"))
