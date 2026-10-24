"""Example GameConfigs for fuzzing and tests (lab only).

Hook functions are top-level so configs can be pickled into harness workers.
"""
from __future__ import annotations

from variant.rules import GameConfig, SpecialStep


def discard_choices(hand, role) -> tuple[str, ...]:
    """After the flop each player with 3 hole cards discards one (choice = card index)."""
    n = len(hand.hole[role])
    return tuple(str(i) for i in range(n)) if n == 3 else ()


def discard_apply(hand, role, choice: str) -> None:
    """The discarded card goes face up onto the board."""
    hand.board.append(hand.hole[role].pop(int(choice)))


DISCARD_STEP = SpecialStep(street=1, name="discard", choices=discard_choices,
                           apply=discard_apply, order=("BB", "SB"))

EXAMPLES: dict[str, GameConfig] = {
    "holdem": GameConfig(),
    "discard3": GameConfig(hole_cards=3, special_steps=(DISCARD_STEP,)),
    "omaha": GameConfig(hole_cards=4, hole_cards_used=2),
    "short_stacks": GameConfig(starting_stack=25),
    "raise_cap": GameConfig(max_raises_per_street=2),
    "persistent": GameConfig(reset_stacks_each_hand=False, starting_stack=200),
    "big_blinds": GameConfig(small_blind=5, big_blind=10, starting_stack=300),
    "extra_street": GameConfig(streets=(0, 3, 1, 1, 0)),
}
