"""★ Variant spec: the complete, JSON-loadable description of a poker variant. ★

On reveal day we write one of these (variant/active.json), validate it, and the engine,
the bot and the tools all compile it into a hand program (bot/game/compile.py).

Sections follow the taxonomy:
  A deck        DeckSpec          ranks, suits, jokers, copies, removed cards
  B/C/F/H       program           ordered list of steps: {"type": ..., params...}
  D evaluation  EvalSpec          hand size, hole-card rules, high/low/hi-lo, wilds, ...
  E betting     BettingSpec       NL/PL/FL, blinds, antes, straddle, caps, sizes
  F payoffs     payoffs           list of {"type": "bounty"|"multiplier"|"rake", ...}
  G match       MatchSpec         hands, bank, stacks, bust, blind schedule
If "program" is omitted it is built from "hole_cards" and "streets" (Hold'em-style).

Pure stdlib (ships with the bot). `validate()` returns every problem in plain English.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional, Union

STANDARD_RANKS = "23456789TJQKA"
STANDARD_SUITS = "cdhs"
CATEGORIES = ["high_card", "pair", "two_pair", "trips", "straight", "flush", "full_house",
              "quads", "straight_flush"]
EVAL_KINDS = ("high", "low_a5", "low_27", "hilo", "score")
STRUCTURES = ("NL", "PL", "FL")
ORDERS = ("BB_first", "SB_first", "simultaneous")

# Step types and their parameters (with defaults). The compiler maps these to plugins.
STEP_PARAMS: dict[str, dict[str, Any]] = {
    "post_blinds": {},
    "deal_hole": {"n": 2, "face_up": 0},
    "deal_board": {"n": 1, "burn": 0, "burn_revealed": False, "boards": None},
    "betting": {"round": "", "first": None},
    "discard": {"n": 1, "order": "BB_first", "visibility": "public", "destination": "board",
                "optional": False},
    "draw": {"max": 1, "min": 0, "cost": 0, "order": "BB_first", "visibility": "private"},
    "swap": {"with": "opponent", "mode": "optional", "n": 1, "probability": 1.0,
             "order": "BB_first", "cost": 0},
    "choose": {"offer": 3, "keep": 1, "order": "BB_first", "visibility": "private"},
    "peek": {"target": "board", "cost": 0, "order": "BB_first"},
    "expose": {"n": 1, "order": "BB_first", "chosen": True},
    "auction": {"kind": "second_price", "prize": "card", "payment": "pot", "tie": "BB",
                "max_bid": None},
    "market": {"quantity": "board_rank_sum", "spread_max": None, "size": 1, "settle_scale": 1},
    "bounty": {"mode": "random", "rank": None, "bonus": 0, "multiplier": 1.0},
    "showdown": {"runs": 1},
}


class SpecError(ValueError):
    """Raised by VariantSpec.check() with every validation message."""


# --------------------------------------------------------------------------- sections

@dataclass
class DeckSpec:
    ranks: str = STANDARD_RANKS         # low to high, e.g. "6789TJQKA" for short deck
    suits: str = STANDARD_SUITS
    jokers: int = 0
    copies: int = 1                     # number of decks shuffled together
    removed: list[str] = field(default_factory=list)   # cards taken out, e.g. ["Ah"]

    @property
    def size(self) -> int:
        return len(self.ranks) * len(self.suits) * self.copies + self.jokers - len(self.removed)


@dataclass
class EvalSpec:
    kind: str = "high"                  # high | low_a5 | low_27 | hilo | score
    hand_size: int = 5
    hole_exact: Optional[int] = None    # Omaha: 2
    hole_min: Optional[int] = None
    hole_max: Optional[int] = None
    category_order: Optional[list[str]] = None   # low to high; e.g. flush above full house
    wild: Optional[dict] = None         # {"jokers": true} | {"rank": "2"} | {"cards": [...]}
    low_qualifier: Optional[int] = None # hi-lo: low must be this rank or better (8 = "8 or better")
    score: Optional[str] = None         # name of a registered custom scoring function
    board_split: str = "even"           # several boards: pot split evenly per board


@dataclass
class BettingSpec:
    structure: str = "NL"               # NL | PL | FL
    small_blind: int = 1
    big_blind: int = 2
    ante: int = 0
    straddle: int = 0                   # 0 = none; else the straddle amount (posted by SB)
    fixed_bets: Optional[list[int]] = None   # FL: bet size per betting round
    max_raises: Optional[int] = None    # per round
    bet_sizes: Optional[list[float]] = None  # allowed bet/raise sizes as pot fractions
    bet_multiple: Optional[int] = None  # bets must be multiples of this
    check_raise: bool = True
    preflop_first: str = "SB"
    postflop_first: str = "BB"


@dataclass
class MatchSpec:
    hands: int = 400
    time_bank_s: float = 60.0
    starting_stack: int = 400
    reset_stacks: bool = True
    bust_ends_match: bool = True
    blind_schedule: list[list[int]] = field(default_factory=list)  # [[from_hand, sb, bb], ...]


@dataclass
class VariantSpec:
    name: str = "holdem"
    description: str = ""
    deck: DeckSpec = field(default_factory=DeckSpec)
    program: list[dict] = field(default_factory=list)
    evaluation: EvalSpec = field(default_factory=EvalSpec)
    betting: BettingSpec = field(default_factory=BettingSpec)
    payoffs: list[dict] = field(default_factory=list)
    match: MatchSpec = field(default_factory=MatchSpec)
    players: int = 2
    # Shorthand used only when `program` is empty:
    hole_cards: int = 2
    streets: list[int] = field(default_factory=lambda: [0, 3, 1, 1])

    # ---- program helpers
    def full_program(self) -> list[dict]:
        """The program with defaults filled in (built from hole_cards/streets if empty)."""
        prog = self.program or default_program(self.hole_cards, self.streets)
        out = []
        for step in prog:
            t = step.get("type")
            merged = dict(STEP_PARAMS.get(t, {}))
            merged.update(step)
            out.append(merged)
        return out

    def step_types(self) -> list[str]:
        return [s["type"] for s in self.full_program()]

    # ---- validation
    def validate(self) -> list[str]:
        return validate(self)

    def check(self) -> "VariantSpec":
        errors = self.validate()
        if errors:
            raise SpecError(f"variant {self.name!r} is invalid:\n  - " + "\n  - ".join(errors))
        return self

    # ---- JSON
    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @staticmethod
    def from_dict(d: dict) -> "VariantSpec":
        d = dict(d)
        unknown = set(d) - {f.name for f in fields(VariantSpec)} - {"_comment"}
        if unknown:
            raise SpecError(f"unknown top-level keys: {sorted(unknown)}")
        d.pop("_comment", None)
        kw: dict[str, Any] = {}
        for f in fields(VariantSpec):
            if f.name not in d:
                continue
            v = d[f.name]
            sub = {"deck": DeckSpec, "evaluation": EvalSpec, "betting": BettingSpec,
                   "match": MatchSpec}.get(f.name)
            kw[f.name] = _build(sub, v, f.name) if sub else v
        return VariantSpec(**kw)

    @staticmethod
    def from_json(text: str) -> "VariantSpec":
        return VariantSpec.from_dict(json.loads(text))

    @staticmethod
    def load(path: Union[str, Path]) -> "VariantSpec":
        return VariantSpec.from_json(Path(path).read_text(encoding="utf-8"))


def _build(cls, value: Any, where: str):
    if not isinstance(value, dict):
        raise SpecError(f"{where}: expected an object")
    names = {f.name for f in fields(cls)}
    unknown = set(value) - names - {"_comment"}
    if unknown:
        raise SpecError(f"{where}: unknown keys {sorted(unknown)} (allowed: {sorted(names)})")
    return cls(**{k: v for k, v in value.items() if k in names})


def default_program(hole_cards: int = 2, streets: list[int] = (0, 3, 1, 1)) -> list[dict]:
    """Hold'em-style program: blinds, hole cards, then (deal, bet) per street, showdown."""
    prog: list[dict] = [{"type": "post_blinds"}, {"type": "deal_hole", "n": hole_cards}]
    names = ["preflop", "flop", "turn", "river"]
    for i, n in enumerate(streets):
        if i > 0:
            prog.append({"type": "deal_board", "n": n})
        prog.append({"type": "betting", "round": names[i] if i < len(names) else f"street{i}"})
    prog.append({"type": "showdown"})
    return prog


# --------------------------------------------------------------------------- validation

def _card_ok(text: str, deck: DeckSpec) -> bool:
    return len(text) == 2 and text[0] in deck.ranks and text[1] in deck.suits


def validate(spec: VariantSpec) -> list[str]:
    """Every problem with the spec, as readable messages (empty list = valid)."""
    e: list[str] = []
    d, ev, b, m = spec.deck, spec.evaluation, spec.betting, spec.match

    # A. deck
    if len(set(d.ranks)) != len(d.ranks) or not d.ranks:
        e.append(f"deck.ranks {d.ranks!r} must be non-empty with no repeats")
    if len(set(d.suits)) != len(d.suits) or not d.suits:
        e.append(f"deck.suits {d.suits!r} must be non-empty with no repeats")
    if d.copies < 1:
        e.append("deck.copies must be at least 1")
    if d.jokers < 0:
        e.append("deck.jokers cannot be negative")
    for c in d.removed:
        if not _card_ok(c, d):
            e.append(f"deck.removed: {c!r} is not a card of this deck")
    if spec.players != 2:
        e.append("only heads-up (players = 2) is supported")

    # program structure
    prog = spec.full_program()
    types = [s.get("type") for s in prog]
    for i, t in enumerate(types):
        if t not in STEP_PARAMS:
            e.append(f"program[{i}]: unknown step type {t!r} (known: {sorted(STEP_PARAMS)})")
        else:
            extra = set(prog[i]) - set(STEP_PARAMS[t]) - {"type"}
            if extra:
                e.append(f"program[{i}] ({t}): unknown parameters {sorted(extra)}")
    if not types or types[-1] != "showdown":
        e.append("program must end with a showdown step")
    if types.count("showdown") > 1:
        e.append("program has more than one showdown step")
    if "betting" not in types:
        e.append("program needs at least one betting step")
    if "post_blinds" not in types and b.ante == 0:
        e.append("program has no post_blinds step and no ante: nothing to win")

    # card accounting through the program
    if not e:
        e += _check_cards(spec, prog)

    # D. evaluation
    if ev.kind not in EVAL_KINDS:
        e.append(f"evaluation.kind {ev.kind!r} unknown (known: {list(EVAL_KINDS)})")
    if not 1 <= ev.hand_size <= 7:
        e.append("evaluation.hand_size must be 1..7")
    if ev.category_order is not None and sorted(ev.category_order) != sorted(CATEGORIES):
        e.append(f"evaluation.category_order must be a permutation of {CATEGORIES}")
    if ev.kind == "score" and not ev.score:
        e.append("evaluation.kind 'score' needs evaluation.score (a registered function name)")
    if ev.low_qualifier is not None and ev.kind not in ("hilo", "low_a5", "low_27"):
        e.append("evaluation.low_qualifier only applies to low or hi-lo evaluation")
    if ev.wild is not None and not ({"jokers", "rank", "cards"} & set(ev.wild)):
        e.append("evaluation.wild needs one of 'jokers', 'rank' or 'cards'")
    if ev.wild and ev.wild.get("jokers") and d.jokers == 0:
        e.append("evaluation.wild uses jokers but the deck has none")
    if d.jokers and not (ev.wild and ev.wild.get("jokers")):
        e.append("deck has jokers but evaluation.wild doesn't make them wild ({'jokers': true})")
    if ev.wild and ev.wild.get("rank") and ev.wild["rank"] not in d.ranks:
        e.append(f"evaluation.wild rank {ev.wild['rank']!r} is not in the deck")

    # E. betting
    if b.structure not in STRUCTURES:
        e.append(f"betting.structure {b.structure!r} unknown (known: {list(STRUCTURES)})")
    if b.small_blind < 0 or b.big_blind <= 0 or b.small_blind > b.big_blind:
        e.append("betting blinds must satisfy 0 <= small_blind <= big_blind, big_blind > 0")
    if b.ante < 0 or b.straddle < 0:
        e.append("betting.ante / straddle cannot be negative")
    if b.straddle and b.straddle < 2 * b.big_blind:
        e.append("betting.straddle must be at least twice the big blind")
    n_rounds = types.count("betting")
    if b.structure == "FL":
        if not b.fixed_bets or len(b.fixed_bets) < n_rounds:
            e.append(f"fixed-limit needs betting.fixed_bets with one size per betting round "
                     f"({n_rounds})")
    if b.max_raises is not None and b.max_raises < 0:
        e.append("betting.max_raises cannot be negative")
    if b.bet_sizes is not None and (not b.bet_sizes or min(b.bet_sizes) <= 0):
        e.append("betting.bet_sizes must be positive pot fractions")
    for k in ("preflop_first", "postflop_first"):
        if getattr(b, k) not in ("SB", "BB"):
            e.append(f"betting.{k} must be 'SB' or 'BB'")

    # F. payoffs
    for i, p in enumerate(spec.payoffs):
        if p.get("type") not in ("bounty", "multiplier", "rake"):
            e.append(f"payoffs[{i}]: unknown type {p.get('type')!r}")

    # G. match
    if m.hands <= 0 or m.time_bank_s <= 0:
        e.append("match.hands and match.time_bank_s must be positive")
    need = b.big_blind + b.ante + b.straddle
    if m.starting_stack <= need:
        e.append(f"match.starting_stack {m.starting_stack} must exceed blinds+ante+straddle ({need})")
    for row in m.blind_schedule:
        if len(row) != 3 or row[0] < 0 or row[1] > row[2] or row[2] <= 0:
            e.append(f"match.blind_schedule entry {row} must be [from_hand, sb, bb] with sb <= bb")
    return e


def _check_cards(spec: VariantSpec, prog: list[dict]) -> list[str]:
    """Walk the program counting cards: never deal more than the deck holds, and have
    enough cards at showdown for the hand-size and hole-card rules."""
    e: list[str] = []
    deck = spec.deck.size
    hole = 0                 # hole cards per player
    board = 0                # cards per board
    boards = 1
    used = 0
    for i, s in enumerate(prog):
        t = s["type"]
        if t == "deal_hole":
            used += s["n"] * spec.players
            hole += s["n"]
            if s["face_up"] > s["n"]:
                e.append(f"program[{i}] deal_hole: face_up {s['face_up']} > n {s['n']}")
        elif t == "deal_board":
            k = s["boards"] or boards
            boards = max(boards, k)
            used += s["n"] * k + s["burn"]
            board += s["n"]
        elif t == "discard":
            if s["n"] > hole:
                e.append(f"program[{i}] discard: discards {s['n']} but players hold {hole}")
            hole -= s["n"]
            if s["destination"] == "board":
                board += s["n"] * spec.players
            elif s["destination"] == "opponent":
                pass   # the opponent receives what we discard: hole count unchanged overall
        elif t == "draw":
            used += s["max"] * spec.players
            if s["max"] > hole:
                e.append(f"program[{i}] draw: draws up to {s['max']} but players hold {hole}")
        elif t == "choose":
            used += s["offer"] * spec.players
            hole += s["keep"]
            if s["keep"] > s["offer"]:
                e.append(f"program[{i}] choose: keep {s['keep']} > offer {s['offer']}")
        elif t == "swap" and s["with"] == "deck":
            used += s["n"] * spec.players
        elif t == "auction" and s["prize"] == "card":
            used += 1
        elif t == "showdown":
            runs = s.get("runs", 1)
            if runs > 1:
                used += (runs - 1) * _runout_after_first_bet(prog) * boards
        if used > deck:
            e.append(f"deck has {deck} cards but the program deals {used} by step {i} ({t})")
            break
    ev = spec.evaluation
    if ev.hand_size > hole + board and ev.kind != "score":
        e.append(f"evaluation.hand_size {ev.hand_size} needs more cards than players have at "
                 f"showdown ({hole} hole + {board} board)")
    if ev.hole_exact is not None:
        if ev.hole_exact > hole:
            e.append(f"evaluation.hole_exact {ev.hole_exact} > hole cards at showdown ({hole})")
        if ev.hand_size - ev.hole_exact > board:
            e.append(f"evaluation needs {ev.hand_size - ev.hole_exact} board cards but the board "
                     f"has {board}")
    return e


def _runout_after_first_bet(prog: list[dict]) -> int:
    """Board cards dealt after the first betting round (what 'run it twice' re-deals)."""
    seen_bet, n = False, 0
    for s in prog:
        if s["type"] == "betting":
            seen_bet = True
        elif s["type"] == "deal_board" and seen_bet:
            n += s["n"]
    return n


def load_catalog(directory: Optional[Path] = None) -> dict[str, VariantSpec]:
    """All presets in variant/catalog/, by name."""
    directory = directory or Path(__file__).resolve().parent / "catalog"
    out = {}
    for path in sorted(directory.glob("*.json")):
        spec = VariantSpec.load(path)
        out[spec.name] = spec
    return out
