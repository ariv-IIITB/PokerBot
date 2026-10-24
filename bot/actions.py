"""Neutral action types plus legality checking and clamping.

Brains return an `Action`; before anything is sent it goes through `clamp`, which turns
any request into something legal (safety layer 2). `safe_action` is the Tier 0 move:
check if free, otherwise fold.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

FOLD = "F"
CHECK = "K"
CALL = "C"
RAISE = "R"      # amount = raise TO this total street contribution
SPECIAL = "S"    # variant-specific action, e.g. a discard; `choice` names the option
KINDS = (FOLD, CHECK, CALL, RAISE, SPECIAL)


@dataclass(frozen=True)
class Action:
    kind: str
    amount: Optional[int] = None
    choice: Optional[str] = None

    @staticmethod
    def fold() -> "Action":
        return Action(FOLD)

    @staticmethod
    def check() -> "Action":
        return Action(CHECK)

    @staticmethod
    def call() -> "Action":
        return Action(CALL)

    @staticmethod
    def raise_to(amount: int) -> "Action":
        return Action(RAISE, amount=amount)

    @staticmethod
    def special(choice: str) -> "Action":
        return Action(SPECIAL, choice=str(choice))


@dataclass(frozen=True)
class SpecialOption:
    """A variant-specific action on offer, e.g. name="discard", choices=("0","1","2")."""
    name: str
    choices: tuple[str, ...]


@dataclass(frozen=True)
class LegalActions:
    fold: bool = False
    check: bool = False
    call: bool = False
    raise_min: Optional[int] = None   # inclusive, "raise to" amounts
    raise_max: Optional[int] = None
    special: Optional[SpecialOption] = None

    @property
    def can_raise(self) -> bool:
        # An inverted range is treated as "no raise" rather than guessing.
        return (self.raise_min is not None and self.raise_max is not None
                and self.raise_min <= self.raise_max)

    @property
    def can_special(self) -> bool:
        return self.special is not None and len(self.special.choices) > 0

    def is_empty(self) -> bool:
        return not (self.fold or self.check or self.call or self.can_raise or self.can_special)


def is_legal(action: Action, legal: LegalActions) -> bool:
    """True if `action` can be sent as-is."""
    if not isinstance(action, Action):
        return False
    k = action.kind
    if k == FOLD:
        return legal.fold
    if k == CHECK:
        return legal.check
    if k == CALL:
        return legal.call
    if k == RAISE:
        return (legal.can_raise and type(action.amount) is int
                and legal.raise_min <= action.amount <= legal.raise_max)  # type: ignore[operator]
    if k == SPECIAL:
        return legal.can_special and action.choice in legal.special.choices  # type: ignore[union-attr]
    return False


def safe_action(legal: LegalActions) -> Action:
    """Tier 0: never puts chips in voluntarily. Always returns something legal if
    anything is legal (fold is returned when nothing is, as a last resort)."""
    if legal.check:
        return Action.check()
    if legal.fold:
        return Action.fold()
    if legal.can_special:
        return Action.special(legal.special.choices[0])  # type: ignore[union-attr]
    if legal.call:
        return Action.call()
    if legal.can_raise:
        return Action.raise_to(legal.raise_min)  # type: ignore[arg-type]
    return Action.fold()


def _to_int(x: object) -> Optional[int]:
    """Coerce a raise amount (int, float, numpy scalar) to int; None if impossible."""
    if isinstance(x, bool):
        return None
    try:
        f = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return int(round(f))


def clamp(action: object, legal: LegalActions) -> Action:
    """Turn any brain output into a legal action, staying as close to its intent as possible.

    - raise: amount clipped into [min, max]; if raising is illegal -> call, else check/fold
    - call when calling is illegal -> check if free, else Tier 0
    - check/fold when illegal -> Tier 0 (check if free, otherwise fold)
    - special: invalid choice -> first offered choice
    - anything else (wrong type, unknown kind) -> Tier 0
    """
    if not isinstance(action, Action):
        return safe_action(legal)
    if is_legal(action, legal):
        return action

    k = action.kind
    if k == RAISE:
        if legal.can_raise:
            amt = _to_int(action.amount)
            if amt is None:
                amt = legal.raise_min
            return Action.raise_to(min(max(amt, legal.raise_min), legal.raise_max))  # type: ignore[type-var]
        if legal.call:
            return Action.call()
        return safe_action(legal)
    if k == CALL:
        return Action.check() if legal.check else safe_action(legal)
    if k == SPECIAL and legal.can_special:
        return Action.special(legal.special.choices[0])  # type: ignore[union-attr]
    return safe_action(legal)
