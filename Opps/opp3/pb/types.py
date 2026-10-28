"""Plain data types shared by the bot core, the local simulator and the adapter.

The bot core never touches engine classes: the adapter (player.py) converts
engine state into an `Obs` and converts our returned action back.
Actions are plain tuples:  ("fold",) ("check",) ("call",) ("raise", raise_to)
`raise_to` is the TOTAL chips committed on the current street after raising
(same convention as the MIT pokerbots engine).
"""
from dataclasses import dataclass
from typing import Optional, Tuple

FOLD = "fold"
CHECK = "check"
CALL = "call"
RAISE = "raise"


@dataclass
class Obs:
    hand_no: int
    hole: Tuple[int, ...]            # card ints 0..51 (rank = c % 13, suit = c // 13)
    board: Tuple[int, ...]           # 0, 3, 4 or 5 cards
    street: int                      # 0 preflop, 1 flop, 2 turn, 3 river
    button: bool                     # True if we are the button / small blind
    pot: int                         # all chips in the middle incl. current-street bets
    hero_pip: int                    # our chips committed on this street
    opp_pip: int
    hero_stack: int                  # chips behind
    opp_stack: int
    to_call: int
    min_raise: int                   # min legal raise_to (0 if cannot raise)
    max_raise: int                   # max legal raise_to (0 if cannot raise)
    can_check: bool
    can_raise: bool
    can_call: bool = True
    can_fold: bool = True
    time_left: Optional[float] = None   # seconds left in the time bank (None = unknown)
    hands_left: int = 1                 # including this one
    bankroll: int = 0                   # our cumulative chips this match
    big_blind: int = 2
    small_blind: int = 1
    start_stack: int = 400


@dataclass
class HandResult:
    delta: int                          # our chips won/lost this hand
    opp_hole: Optional[Tuple[int, ...]] = None   # revealed only at showdown
    board: Tuple[int, ...] = ()
    hero_folded: bool = False
