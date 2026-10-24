"""★ Variant rules. Edit this file (only) when the real variant is revealed. ★

`GameConfig` describes the game; the engine, the equity code and the bots read the street
structure and hand rules from it instead of hardcoding Hold'em numbers.
Placeholder defaults = heads-up No-Limit Texas Hold'em.

Special steps (e.g. a discard) are optional hooks the engine runs on a given street,
before or after that street's betting round. None by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class SpecialStep:
    """A non-betting decision step, e.g. "each player discards one hole card".

    The engine asks each role in `order` (skipping folded players) for a choice:
      choices(hand, role) -> tuple of option strings (empty tuple = skip this player)
      apply(hand, role, choice) -> mutate the engine's hand (hole / board / deck lists)
    `hand` is the lab engine's hand object (attributes: hole[role], board, deck, ...).
    The chosen option is shown to the opponent as `OPP type=S choice=...`; any changes to
    the board are broadcast, changes to a player's hole cards are sent to that player.
    """
    street: int
    name: str
    choices: Callable[[Any, int], tuple[str, ...]]
    apply: Callable[[Any, int, str], None]
    order: tuple[str, ...] = ("BB", "SB")
    timing: str = "before_betting"     # or "after_betting"


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

    # --- variant hooks
    special_steps: tuple[SpecialStep, ...] = ()

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
