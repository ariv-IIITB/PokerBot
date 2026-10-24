"""Mock protocol #2: terse single-letter lines, "raise BY", dealer/big-blind seat names.

Engine -> bot (fields separated by spaces, cards concatenated "AhKd", "-" = none):
  M <hands> <bank> <sb> <bb> <stack>
  H <id> <D|B> <stack> <oppstack> [<timeleft>] [L<sb>,<bb>,<ante>]
                                                   D = dealer (small blind), B = big blind
  C <cards>                                        our hole cards
  T <street> <cards> [<board index>]               the board so far
  O <f|k|c|r<to>|s:<choice>>                       opponent action (raises as new TOTAL)
  A <pot> <tocall> <mybet> <oppbet> <mystack> <oppstack> <legal> [<timeleft>]
       legal: tokens joined by "/": f k c  r<min>~<max>  (raise BY amounts: the raise on
       top of calling; "r<min>~<max>^<m>": raise-to amounts must be multiples of m, or
       all-in; "r=<a>|<b>|<c>": only these BY amounts)  s:<name>:<a>|<b>  or  s:<name>:<lo>~<hi>
  X <cards>   I <kind> <me|opp|none> <cards> [<value>]   E <delta>   Z
Bot -> engine: f | k | c | r<by> | s:<choice>
"raise BY" b means: put in enough to call, plus b more  ->  raise TO = highest bet + b.
"""
from __future__ import annotations


from bot.actions import (CALL, CHECK, FOLD, RAISE, SPECIAL, Action, LegalActions,
                         SpecialOption)
from bot.cards import format_card, parse_card
from bot.protocol import (ActRequest, BoardUpdate, HandEnd, HandStart, HoleCards, Info,
                          MatchEnd, MatchInfo, OppAction, ProtocolError, Showdown)
from bot.protocols.base import Adapter

SEATS = {0: "D", 1: "B"}
SEAT_IDS = {"D": 0, "B": 1}


def _cards(cards) -> str:
    return "".join(format_card(c) for c in cards) or "-"


def _parse_cards(s: str) -> tuple[int, ...]:
    if s == "-":
        return ()
    out, i = [], 0
    while i < len(s):
        j = i + 2
        if j < len(s) and s[j] == "~":           # copy suffix, e.g. "Ah~1"
            j += 1
            while j < len(s) and s[j].isdigit():
                j += 1
        out.append(parse_card(s[i:j]))
        i = j
    return tuple(out)


def _act_token(a: Action, high: int = 0, by: bool = True) -> str:
    if a.kind == RAISE:
        return f"r{a.amount - high if by else a.amount}"
    if a.kind == SPECIAL:
        return f"s:{a.choice}"
    return {FOLD: "f", CHECK: "k", CALL: "c"}[a.kind]


def _parse_act_token(t: str, high: int = 0, by: bool = True) -> Action:
    if t in ("f", "k", "c"):
        return Action({"f": FOLD, "k": CHECK, "c": CALL}[t])
    if t.startswith("r") and t[1:].lstrip("-").isdigit():
        n = int(t[1:])
        return Action.raise_to(high + n if by else n)
    if t.startswith("s:") and len(t) > 2:
        return Action.special(t[2:])
    raise ProtocolError(f"bad action token {t!r}")


def _legal_token(L: LegalActions, high: int) -> str:
    parts = [k for k, ok in (("f", L.fold), ("k", L.check), ("c", L.call)) if ok]
    if L.raise_min is not None and L.raise_max is not None:
        if L.raise_sizes:
            parts.append("r=" + "|".join(str(a - high) for a in L.raise_sizes))
        else:
            step = f"^{L.raise_step}" if L.raise_step else ""
            parts.append(f"r{L.raise_min - high}~{L.raise_max - high}{step}")
    if L.special is not None:
        sp = L.special
        opts = f"{sp.lo}~{sp.hi}" if sp.is_range else "|".join(sp.choices)
        parts.append(f"s:{sp.name}:{opts}")
    return "/".join(parts) or "-"


def _parse_legal(t: str, high: int) -> LegalActions:
    fold = check = call = False
    rmin = rmax = None
    special = None
    sizes = step = None
    if t != "-":
        for part in t.split("/"):
            if part == "f":
                fold = True
            elif part == "k":
                check = True
            elif part == "c":
                call = True
            elif part.startswith("r="):
                sizes = tuple(high + int(x) for x in part[2:].split("|"))
                rmin, rmax = min(sizes), max(sizes)
            elif part.startswith("r"):
                body, caret, st = part[1:].partition("^")
                lo, sep, hi = body.partition("~")
                if not sep:
                    raise ProtocolError(f"bad raise range {part!r}")
                rmin, rmax = high + int(lo), high + int(hi)
                step = int(st) if caret else None
            elif part.startswith("s:"):
                _, name, opts = part.split(":", 2)
                lo, sep, hi = opts.partition("~")
                if sep and lo.isdigit() and hi.isdigit():
                    special = SpecialOption(name, (), int(lo), int(hi))
                else:
                    special = SpecialOption(name, tuple(opts.split("|")))
            else:
                raise ProtocolError(f"bad legal token {part!r}")
    return LegalActions(fold, check, call, rmin, rmax, special, sizes, step)


class TerseAdapter(Adapter):
    name = "terse"

    def __init__(self) -> None:
        self.high = 0            # highest street bet at the last ACT (both sides track it)

    # ---- engine side
    def encode_message(self, m) -> str:
        if isinstance(m, MatchInfo):
            return f"M {m.hands} {m.timebank!r} {m.sb} {m.bb} {m.stack}"
        if isinstance(m, HandStart):
            t = f" {m.timeleft:.4f}" if m.timeleft is not None else ""
            lv = f" L{m.sb},{m.bb},{m.ante}" if m.bb is not None else ""
            return f"H {m.hand_id} {SEATS[m.seat]} {m.stack} {m.oppstack}{t}{lv}"
        if isinstance(m, HoleCards):
            return f"C {_cards(m.cards)}"
        if isinstance(m, BoardUpdate):
            idx = f" {m.index}" if m.index is not None else ""
            return f"T {m.street} {_cards(m.cards)}{idx}"
        if isinstance(m, OppAction):
            return f"O {_act_token(m.action, by=False)}"
        if isinstance(m, ActRequest):
            mybet = m.mybet if m.mybet is not None else 0
            oppbet = m.oppbet if m.oppbet is not None else 0
            self.high = max(mybet, oppbet)
            t = f" {m.timeleft:.4f}" if m.timeleft is not None else ""
            return (f"A {m.pot} {m.tocall} {mybet} {oppbet} {m.mystack} {m.oppstack} "
                    f"{_legal_token(m.legal, self.high)}{t}")
        if isinstance(m, Showdown):
            return f"X {_cards(m.oppcards)}"
        if isinstance(m, Info):
            v = f" {m.value}" if m.value is not None else ""
            return f"I {m.kind} {m.who} {_cards(m.cards)}{v}"
        if isinstance(m, HandEnd):
            return f"E {m.delta}"
        if isinstance(m, MatchEnd):
            return "Z"
        raise TypeError(f"not a message: {m!r}")

    def parse_action(self, line: str) -> Action:
        t = line.strip()
        if not t or " " in t:
            raise ProtocolError(f"bad reply {line!r}")
        return _parse_act_token(t, self.high, by=True)

    # ---- bot side
    def parse_line(self, line: str):
        tok = line.split()
        if not tok:
            return None
        tag, f = tok[0], tok[1:]
        try:
            if tag == "M":
                return MatchInfo(int(f[0]), float(f[1]), int(f[2]), int(f[3]), int(f[4]))
            if tag == "H":
                level = [x for x in f[4:] if x.startswith("L")]
                rest = [x for x in f[4:] if not x.startswith("L")]
                sb = bb = ante = None
                if level:
                    sb, bb, ante = (int(x) for x in level[0][1:].split(","))
                return HandStart(int(f[0]), SEAT_IDS[f[1]], int(f[2]), int(f[3]),
                                 float(rest[0]) if rest else None, sb, bb, ante)
            if tag == "C":
                return HoleCards(_parse_cards(f[0]))
            if tag == "T":
                return BoardUpdate(int(f[0]), _parse_cards(f[1]), int(f[2]) if len(f) > 2 else None)
            if tag == "O":
                return OppAction(_parse_act_token(f[0], by=False))
            if tag == "A":
                mybet, oppbet = int(f[2]), int(f[3])
                self.high = max(mybet, oppbet)
                return ActRequest(int(f[0]), int(f[1]), int(f[4]), int(f[5]),
                                  _parse_legal(f[6], self.high),
                                  float(f[7]) if len(f) > 7 else None, mybet, oppbet)
            if tag == "X":
                return Showdown(_parse_cards(f[0]))
            if tag == "I":
                return Info(f[0], f[1], _parse_cards(f[2]), int(f[3]) if len(f) > 3 else None)
            if tag == "E":
                return HandEnd(int(f[0]))
            if tag == "Z":
                return MatchEnd()
        except (IndexError, KeyError, ValueError) as e:
            raise ProtocolError(f"bad {tag} line {line.strip()!r}: {e}") from None
        return None

    def encode_action(self, action: Action) -> str:
        return _act_token(action, self.high, by=True)
