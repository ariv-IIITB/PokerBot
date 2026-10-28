"""Scenario kit: play one hand through bot/game on a rigged deck and assert it step by step.

    Scenario(
        spec="holdem_nl",                                    # catalog name or a spec JSON path
        holes={"SB": ["As", "Kd"], "BB": ["Qs", "9h"]},      # SB = button, acts first preflop
        board=["Ah", "7d", "2s", "3c", "4h"],
        steps=[("SB", "raise 6", {"legal": {"fold", "call", "raise"}, "min": 4}),
               ("BB", "call", {}), ...],
        expect={"deltas": {"SB": 12, "BB": -12}, "showdown": False},
    )

Actions: fold | check | call | raise N (raise TO N) | discard Kd (hole card names, "Kd,7c" for
several) | special TOKEN (the raw option token). Expectations before acting (all optional):
legal (set of names), min, max, street (state street number), pot, tocall, stack, bet,
options (special tokens offered). Final expectations: deltas {role: chips}, showdown, folded
(role), pot, muck (cards), hole {role: cards} (what each player still holds).

run_scenario() also checks chip conservation, that every step was consumed and the hand is
over, and that no player's view contains a card they may not know. A mismatch names the step.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from bot.actions import Action, LegalActions
from bot.cards import format_card, parse_card, remaining_deck
from bot.game.observation import hidden_from, observe
from bot.game.rules_spec import to_rules
from bot.game.runner import act, advance, legal_actions
from bot.game.state import GameState
from variant.spec import VariantSpec, load_catalog

ROLES = {"SB": 0, "BB": 1}
ROLE_NAMES = ("SB", "BB")
STREET_NAMES = ("preflop", "flop", "turn", "river")


class ScenarioError(AssertionError):
    """The hand did not go as the scenario said; the message names the step."""


@dataclass
class Scenario:
    spec: str
    holes: dict[str, Sequence[str]]
    board: Sequence[str] = ()
    steps: Sequence[tuple] = ()
    expect: dict[str, Any] = field(default_factory=dict)
    stacks: Optional[tuple[int, int]] = None      # default: the spec's starting stack, both
    hand_id: int = 0


def load_spec(spec: str) -> VariantSpec:
    if Path(spec).is_file():
        return VariantSpec.load(spec)
    return load_catalog()[spec]


def rigged_deck(rules, holes: dict[str, Sequence[str]], board: Sequence[str]) -> list[int]:
    """The deck order the engine deals from: SB's hole cards, BB's, then the board in
    order (lab/engine.py deals by role); the rest of the deck follows."""
    cards = [parse_card(c) for r in ROLE_NAMES for c in holes[r]]
    cards += [parse_card(c) for c in board]
    if len(set(cards)) != len(cards):
        raise ValueError(f"scenario repeats a card: {[format_card(c) for c in cards]}")
    rest = [c for c in (rules.deck or remaining_deck()) if c not in cards]
    return cards + rest


def parse_step_action(text: str, st: GameState, p: int) -> Action:
    """'raise 6' -> Action; 'discard Kd' -> the special token indexing p's hole cards."""
    word, _, arg = text.strip().partition(" ")
    word, arg = word.lower(), arg.strip()
    if word == "fold":
        return Action.fold()
    if word == "check":
        return Action.check()
    if word == "call":
        return Action.call()
    if word == "raise":
        return Action.raise_to(int(arg))
    if word == "special":
        return Action.special(arg)
    if word == "discard":
        hole = list(st.hole[p])
        idx = sorted(hole.index(parse_card(c)) for c in arg.split(","))
        return Action.special("+".join(str(i) for i in idx))
    raise ValueError(f"unknown scenario action {text!r}")


def legal_names(legal: LegalActions) -> set[str]:
    names = {n for n in ("fold", "check", "call") if getattr(legal, n)}
    if legal.can_raise:
        names.add("raise")
    if legal.can_special:
        names.add(legal.special.name)             # type: ignore[union-attr]
    return names


def _cards(xs) -> list[int]:
    return sorted(parse_card(c) for c in xs)


def run_scenario(s: Scenario) -> GameState:
    """Play the scenario; returns the finished GameState. Raises ScenarioError on a mismatch."""
    rules = to_rules(load_spec(s.spec))
    stacks = list(s.stacks or (rules.starting_stack, rules.starting_stack))
    deck = rigged_deck(rules, s.holes, s.board)
    st = GameState(rules, deck, stacks, s.hand_id, audit=True)
    initial_hole = {r: _cards(s.holes[r]) for r in ROLE_NAMES}

    for i, step in enumerate(s.steps):
        who, text = step[0], step[1]
        want: dict = step[2] if len(step) > 2 else {}
        tag = f"step {i} ({who}: {text})"
        p = advance(st)
        if p is None:
            raise ScenarioError(f"{tag}: the hand is already over")
        if p != ROLES[who]:
            raise ScenarioError(f"{tag}: {ROLE_NAMES[p]} is to act, not {who}")
        legal = legal_actions(st, p)
        _check_before(tag, st, p, legal, want)
        action = parse_step_action(text, st, p)
        try:
            act(st, p, action)
        except Exception as e:                      # an illegal scripted action is a test bug
            raise ScenarioError(f"{tag}: engine rejected the action: {e!r}") from e
    p = advance(st)
    if p is not None:
        raise ScenarioError(f"scenario ended but {ROLE_NAMES[p]} still has to act "
                            f"(legal {sorted(legal_names(legal_actions(st, p)))})")
    _check_end(s, st, initial_hole)
    return st


def _check_before(tag: str, st: GameState, p: int, legal: LegalActions, want: dict) -> None:
    got = {
        "legal": legal_names(legal),
        "min": legal.raise_min if legal.can_raise else None,
        "max": legal.raise_max if legal.can_raise else None,
        "street": st.street,
        "pot": st.pot,
        "tocall": st.to_call(p),
        "stack": st.stack[p],
        "bet": st.bet[p],
        "options": tuple(legal.special.choices) if legal.can_special else (),
    }
    for key, expected in want.items():
        if key not in got:
            raise ScenarioError(f"{tag}: unknown expectation {key!r}")
        if key == "legal":
            expected = set(expected)
        if key == "street" and isinstance(expected, str):
            expected = STREET_NAMES.index(expected)
        if got[key] != expected:
            raise ScenarioError(f"{tag}: expected {key}={expected!r} before acting, got "
                                f"{got[key]!r}")


def _check_end(s: Scenario, st: GameState, initial_hole: dict) -> None:
    if st.deltas is None or sum(st.deltas) + st.house != 0:
        raise ScenarioError(f"chips not conserved: deltas {st.deltas}, house {st.house}")
    want = s.expect
    if "deltas" in want:
        got = {r: st.deltas[ROLES[r]] for r in ROLE_NAMES}
        if got != {r: want["deltas"].get(r, got[r]) for r in ROLE_NAMES}:
            raise ScenarioError(f"deltas: expected {want['deltas']}, got {got}")
    if "showdown" in want and st.showdown != want["showdown"]:
        raise ScenarioError(f"showdown: expected {want['showdown']}, got {st.showdown}")
    if "folded" in want:
        got = None if st.folded is None else ROLE_NAMES[st.folded]
        if got != want["folded"]:
            raise ScenarioError(f"folded: expected {want['folded']}, got {got}")
    if "pot" in want and st.pot != want["pot"]:
        raise ScenarioError(f"pot: expected {want['pot']}, got {st.pot}")
    if "muck" in want and sorted(st.muck) != _cards(want["muck"]):
        raise ScenarioError(f"muck: expected {sorted(want['muck'])}, got "
                            f"{[format_card(c) for c in st.muck]}")
    for r, cards in want.get("hole", {}).items():
        if sorted(st.hole[ROLES[r]]) != _cards(cards):
            raise ScenarioError(f"{r} hole: expected {list(cards)}, got "
                                f"{[format_card(c) for c in st.hole[ROLES[r]]]}")
    # No player's view contains a card they may not know (undealt or the other's hole).
    for p in (0, 1):
        leaked = observe(st, p).seen_cards & hidden_from(st, p)
        if leaked:
            raise ScenarioError(f"{ROLE_NAMES[p]} saw hidden cards "
                                f"{[format_card(c) for c in sorted(leaked)]}")
