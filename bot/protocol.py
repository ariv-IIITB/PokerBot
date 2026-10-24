"""Placeholder wire protocol — the ONLY bot file that knows the text format.

When the real engine protocol is revealed, rewrite this file (and keep the neutral
message classes so the rest of the bot is untouched). The lab engine imports the
encode helpers from here, so both sides always speak the same format.

Format: one message per line, a tag followed by KEY=value tokens. Cards "Ah,Kd", "-" = none.

Engine -> bot:
    MATCH hands=400 timebank=60.0 sb=1 bb=2 stack=400
    HAND id=17 seat=0 stack=400 oppstack=400 timeleft=55.21     (seat 0 = small blind;
                                       optional sb= bb= ante=: this hand's blinds)
    HOLE cards=Ah,Kd
    BOARD street=1 cards=Ts,9h,2c                               (full board so far)
    OPP type=R amount=6                                         (F/K/C/R/S; S uses choice=)
    ACT pot=9 tocall=4 mystack=398 oppstack=394 legal=F,C,R:8-400 timeleft=55.21
        (optional: mybet= oppbet= = chips each side has put in on this street;
         pot = everything committed this hand, including the current street)
    SHOW oppcards=Qs,Qd
    INFO kind=expose who=opp cards=Ah        (information outside HOLE/BOARD/SHOW:
                                              kind = expose | peek | reveal | burn | offer |
                                              run | bounty | auction | market | payment,
                                              who = me | opp | none, optional value=<int>)
    BOARD ... index=1                        (several boards: which one)
    END delta=-6
    ENDMATCH
Bot -> engine (only in reply to ACT): F | K | C | R <amount> | S <choice>

Special steps (variant card steps) appear in ACT as legal=S:<step>:<opt>|<opt>|...
with option tokens (no spaces/commas/pipes):
    "0", "0+2"   hole-card indices into my current hole cards (discard / draw / expose /
                 swap) or into the offered cards (choose)
    "none"       do nothing;  "yes" / "no"  (peek);  "h1b3"  swap hole 1 with board card 3
    "0-50"       a numeric range (bids, quotes): reply with any integer in it, e.g. "S 17"
The opponent's choice arrives as OPP type=S choice=<token>, or choice=hidden for private
steps (draw shows the number of cards drawn instead).

Unknown tags and unknown keys are ignored (parse_line returns None / skips them).
Known tags with missing or bad values raise ProtocolError.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from bot.actions import (CALL, CHECK, FOLD, RAISE, SPECIAL, Action, LegalActions,
                         SpecialOption)
from bot.cards import format_cards, parse_cards


class ProtocolError(ValueError):
    """A line (or reply) that looks like a known message but can't be parsed."""


# --------------------------------------------------------------------------- messages

@dataclass(frozen=True)
class MatchInfo:
    hands: int = 400
    timebank: float = 60.0
    sb: int = 1
    bb: int = 2
    stack: int = 400


@dataclass(frozen=True)
class HandStart:
    hand_id: int
    seat: int
    stack: int
    oppstack: int
    timeleft: Optional[float] = None
    sb: Optional[int] = None        # this hand's blinds/ante, when they can change
    bb: Optional[int] = None
    ante: Optional[int] = None


@dataclass(frozen=True)
class HoleCards:
    cards: tuple[int, ...]


@dataclass(frozen=True)
class BoardUpdate:
    street: int
    cards: tuple[int, ...]
    index: Optional[int] = None     # which board, when several are dealt


@dataclass(frozen=True)
class OppAction:
    action: Action


@dataclass(frozen=True)
class ActRequest:
    pot: int
    tocall: int
    mystack: int
    oppstack: int
    legal: LegalActions
    timeleft: Optional[float] = None
    mybet: Optional[int] = None     # our chips in on this street
    oppbet: Optional[int] = None


@dataclass(frozen=True)
class Showdown:
    oppcards: tuple[int, ...]


@dataclass(frozen=True)
class Info:
    kind: str                     # expose | peek | reveal | burn | offer | run | bounty |
    who: str                      #   auction | market | payment;   who: me | opp | none
    cards: tuple[int, ...] = ()
    value: Optional[int] = None   # numbers: bounty rank, auction price, market value, ...


@dataclass(frozen=True)
class HandEnd:
    delta: int


@dataclass(frozen=True)
class MatchEnd:
    pass


Message = Union[MatchInfo, HandStart, HoleCards, BoardUpdate, OppAction, ActRequest,
                Showdown, Info, HandEnd, MatchEnd]


# --------------------------------------------------------------------------- helpers

def _kv(tokens: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for tok in tokens:
        key, sep, val = tok.partition("=")
        if not sep or not key:
            raise ProtocolError(f"bad token {tok!r}")
        out[key] = val
    return out


def _get(kv: dict[str, str], key: str, conv, default=None, required: bool = True):
    if key not in kv:
        if required:
            raise ProtocolError(f"missing {key}=")
        return default
    try:
        return conv(kv[key])
    except (ValueError, TypeError) as e:
        raise ProtocolError(f"bad {key}={kv[key]!r}: {e}") from None


def parse_legal(text: str) -> LegalActions:
    """Parse e.g. "F,C,R:8-400", "R:8-400/2" (multiples of 2, or all-in),
    "R:6|12|400" (only these amounts), "S:discard:0|1|2" or "-" (nothing legal)."""
    fold = check = call = False
    rmin = rmax = None
    sizes = step = None
    special = None
    if text.strip() in ("", "-"):
        return LegalActions()
    for part in text.split(","):
        head, _, rest = part.partition(":")
        if head == FOLD and not rest:
            fold = True
        elif head == CHECK and not rest:
            check = True
        elif head == CALL and not rest:
            call = True
        elif head == RAISE:
            try:
                if "|" in rest:
                    sizes = tuple(int(x) for x in rest.split("|"))
                    rmin, rmax = min(sizes), max(sizes)
                else:
                    rng, slash, st = rest.partition("/")
                    lo, dash, hi = rng.partition("-")
                    if not dash:
                        raise ValueError
                    rmin, rmax = int(lo), int(hi)
                    step = int(st) if slash else None
            except ValueError:
                raise ProtocolError(f"bad raise range {part!r}") from None
        elif head == SPECIAL:
            name, colon, choices = rest.partition(":")
            if not colon or not name or not choices:
                raise ProtocolError(f"bad special {part!r}")
            lo, dash, hi = choices.partition("-")
            if dash and "|" not in choices and lo.isdigit() and hi.isdigit():
                special = SpecialOption(name, (), int(lo), int(hi))      # numeric range
            else:
                special = SpecialOption(name, tuple(choices.split("|")))
        else:
            raise ProtocolError(f"unknown legal token {part!r}")
    return LegalActions(fold, check, call, rmin, rmax, special, sizes, step)


def format_legal(legal: LegalActions) -> str:
    parts = []
    if legal.fold:
        parts.append(FOLD)
    if legal.check:
        parts.append(CHECK)
    if legal.call:
        parts.append(CALL)
    if legal.raise_min is not None and legal.raise_max is not None:
        if legal.raise_sizes:
            parts.append(f"{RAISE}:{'|'.join(str(a) for a in legal.raise_sizes)}")
        else:
            step = f"/{legal.raise_step}" if legal.raise_step else ""
            parts.append(f"{RAISE}:{legal.raise_min}-{legal.raise_max}{step}")
    if legal.special is not None:
        sp = legal.special
        opts = f"{sp.lo}-{sp.hi}" if sp.is_range else "|".join(sp.choices)
        parts.append(f"{SPECIAL}:{sp.name}:{opts}")
    return ",".join(parts) if parts else "-"


# --------------------------------------------------------------------------- engine -> bot

def parse_line(line: str) -> Optional[Message]:
    """Parse one engine line. Returns None for blank/unknown lines; raises ProtocolError
    for a known tag with bad contents."""
    tokens = line.split()
    if not tokens:
        return None
    tag, rest = tokens[0], tokens[1:]
    if tag == "ENDMATCH":
        return MatchEnd()
    if tag not in _PARSERS:
        return None
    try:
        return _PARSERS[tag](_kv(rest))
    except ProtocolError:
        raise
    except ValueError as e:  # e.g. bad cards
        raise ProtocolError(str(e)) from None


def _p_match(kv):
    d = MatchInfo()
    return MatchInfo(
        hands=_get(kv, "hands", int, d.hands, required=False),
        timebank=_get(kv, "timebank", float, d.timebank, required=False),
        sb=_get(kv, "sb", int, d.sb, required=False),
        bb=_get(kv, "bb", int, d.bb, required=False),
        stack=_get(kv, "stack", int, d.stack, required=False),
    )


def _p_hand(kv):
    return HandStart(_get(kv, "id", int), _get(kv, "seat", int), _get(kv, "stack", int),
                     _get(kv, "oppstack", int),
                     _get(kv, "timeleft", float, None, required=False),
                     _get(kv, "sb", int, None, required=False),
                     _get(kv, "bb", int, None, required=False),
                     _get(kv, "ante", int, None, required=False))


def _p_opp(kv):
    kind = _get(kv, "type", str)
    if kind == RAISE:
        return OppAction(Action.raise_to(_get(kv, "amount", int)))
    if kind == SPECIAL:
        return OppAction(Action.special(_get(kv, "choice", str)))
    if kind in (FOLD, CHECK, CALL):
        return OppAction(Action(kind))
    raise ProtocolError(f"bad OPP type {kind!r}")


def _p_act(kv):
    return ActRequest(_get(kv, "pot", int), _get(kv, "tocall", int),
                      _get(kv, "mystack", int), _get(kv, "oppstack", int),
                      parse_legal(_get(kv, "legal", str)),
                      _get(kv, "timeleft", float, None, required=False),
                      _get(kv, "mybet", int, None, required=False),
                      _get(kv, "oppbet", int, None, required=False))


_PARSERS = {
    "MATCH": _p_match,
    "HAND": _p_hand,
    "HOLE": lambda kv: HoleCards(_get(kv, "cards", parse_cards)),
    "BOARD": lambda kv: BoardUpdate(_get(kv, "street", int), _get(kv, "cards", parse_cards),
                                    _get(kv, "index", int, None, required=False)),
    "OPP": _p_opp,
    "ACT": _p_act,
    "SHOW": lambda kv: Showdown(_get(kv, "oppcards", parse_cards)),
    "INFO": lambda kv: Info(_get(kv, "kind", str), _get(kv, "who", str, "none", required=False),
                            _get(kv, "cards", parse_cards, (), required=False),
                            _get(kv, "value", int, None, required=False)),
    "END": lambda kv: HandEnd(_get(kv, "delta", int)),
}


def encode_message(msg: Message) -> str:
    """Engine side: message object -> line (no trailing newline)."""
    if isinstance(msg, MatchInfo):
        return (f"MATCH hands={msg.hands} timebank={float(msg.timebank)!r} "
                f"sb={msg.sb} bb={msg.bb} stack={msg.stack}")
    if isinstance(msg, HandStart):
        s = f"HAND id={msg.hand_id} seat={msg.seat} stack={msg.stack} oppstack={msg.oppstack}"
        for key in ("sb", "bb", "ante"):
            if getattr(msg, key) is not None:
                s += f" {key}={getattr(msg, key)}"
        return s + (f" timeleft={msg.timeleft:.4f}" if msg.timeleft is not None else "")
    if isinstance(msg, HoleCards):
        return f"HOLE cards={format_cards(msg.cards)}"
    if isinstance(msg, BoardUpdate):
        idx = f" index={msg.index}" if msg.index is not None else ""
        return f"BOARD street={msg.street} cards={format_cards(msg.cards)}{idx}"
    if isinstance(msg, OppAction):
        a = msg.action
        if a.kind == RAISE:
            return f"OPP type=R amount={a.amount}"
        if a.kind == SPECIAL:
            return f"OPP type=S choice={a.choice}"
        return f"OPP type={a.kind}"
    if isinstance(msg, ActRequest):
        s = (f"ACT pot={msg.pot} tocall={msg.tocall} mystack={msg.mystack} "
             f"oppstack={msg.oppstack} legal={format_legal(msg.legal)}")
        if msg.mybet is not None and msg.oppbet is not None:
            s += f" mybet={msg.mybet} oppbet={msg.oppbet}"
        return s + (f" timeleft={msg.timeleft:.4f}" if msg.timeleft is not None else "")
    if isinstance(msg, Showdown):
        return f"SHOW oppcards={format_cards(msg.oppcards)}"
    if isinstance(msg, Info):
        val = f" value={msg.value}" if msg.value is not None else ""
        return f"INFO kind={msg.kind} who={msg.who} cards={format_cards(msg.cards)}{val}"
    if isinstance(msg, HandEnd):
        return f"END delta={msg.delta}"
    if isinstance(msg, MatchEnd):
        return "ENDMATCH"
    raise TypeError(f"not a message: {msg!r}")


# --------------------------------------------------------------------------- bot -> engine

def encode_action(action: Action) -> str:
    """Bot side: Action -> reply line (no trailing newline)."""
    if action.kind == RAISE:
        return f"R {int(action.amount)}"  # type: ignore[arg-type]
    if action.kind == SPECIAL:
        return f"S {action.choice}"
    if action.kind in (FOLD, CHECK, CALL):
        return action.kind
    raise ValueError(f"bad action {action!r}")


def parse_action(line: str) -> Action:
    """Engine side: reply line -> Action. Raises ProtocolError on anything malformed
    (legality is checked separately by the engine)."""
    tokens = line.split()
    if not tokens:
        raise ProtocolError("empty reply")
    kind, args = tokens[0], tokens[1:]
    if kind in (FOLD, CHECK, CALL) and not args:
        return Action(kind)
    if kind == RAISE and len(args) == 1:
        try:
            return Action.raise_to(int(args[0]))
        except ValueError:
            raise ProtocolError(f"bad raise amount {args[0]!r}") from None
    if kind == SPECIAL and len(args) == 1:
        return Action.special(args[0])
    raise ProtocolError(f"bad reply {line!r}")
