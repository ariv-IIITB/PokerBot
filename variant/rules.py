"""★ Variant rules. Edit this file (only) when the real variant is revealed. ★

`GameConfig` describes the game; the engine, the equity code and the bots read the street
structure and hand rules from it instead of hardcoding Hold'em numbers.
Placeholder defaults = heads-up No-Limit Texas Hold'em.

Special-action hooks (e.g. a discard step) are added to GameConfig in phase 5.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GameConfig:
    # --- cards
    hole_cards: int = 2
    streets: tuple[int, ...] = (0, 3, 1, 1)   # new board cards per street; street 0 = preflop
    hand_size: int = 5                         # best k-card hand wins
    hole_cards_used: Optional[int] = None      # None = any number; e.g. 2 for Omaha-style

    # --- chips
    small_blind: int = 1
    big_blind: int = 2
    starting_stack: int = 400
    reset_stacks_each_hand: bool = True

    # --- betting
    min_raise_rule: str = "last_raise"         # min raise increment = size of the last raise
    max_raises_per_street: Optional[int] = None
    preflop_first_actor: str = "SB"            # heads-up: SB/button acts first preflop
    postflop_first_actor: str = "BB"

    # --- match
    hands_per_match: int = 400
    time_bank_s: float = 60.0

    def __post_init__(self) -> None:
        if self.hole_cards_used is not None:
            if not 0 <= self.hole_cards_used <= min(self.hole_cards, self.hand_size):
                raise ValueError("hole_cards_used out of range")
            if self.hand_size - self.hole_cards_used > self.board_cards:
                raise ValueError("not enough board cards for hole_cards_used")
        if self.hole_cards + self.board_cards < self.hand_size:
            raise ValueError("fewer cards than hand_size")

    @property
    def board_cards(self) -> int:
        """Total board cards by the river."""
        return sum(self.streets)

    @property
    def num_streets(self) -> int:
        return len(self.streets)

    def board_after(self, street: int) -> int:
        """Board size once `street` has been dealt."""
        return sum(self.streets[: street + 1])


DEFAULT_CONFIG = GameConfig()
