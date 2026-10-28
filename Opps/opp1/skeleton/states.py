"""
Game and round states for Heads-Up No-Limit Texas Hold'em.
"""

from collections import namedtuple
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction

STARTING_STACK = 200
BIG_BLIND = 2
SMALL_BLIND = 1
NUM_ROUNDS = 400

GameState = namedtuple("GameState", ["bankroll", "game_clock", "round_num"])
TerminalState = namedtuple("TerminalState", ["deltas", "previous_state"])


class RoundState(namedtuple("_RoundState", [
    "button",
    "street",
    "pips",
    "stacks",
    "hands",
    "deck",
    "previous_state"
])):
    """
    Represents the full betting round state in Heads-Up No-Limit Hold'em.
    
    Attributes:
        button: 0 or 1, which player is dealer/button.
        street: 0 (preflop), 3 (flop), 4 (turn), 5 (river).
        pips: (pip_0, pip_1) - chips committed on current street.
        stacks: (stack_0, stack_1) - remaining stack size for each player.
        hands: (hand_0, hand_1) - hole cards for each player (or None if hidden).
        deck: list of community cards on the board.
        previous_state: preceding RoundState or None.
    """

    def legal_actions(self):
        """
        Returns the set of legal action classes for the active player.
        In HU Hold'em, the active player depends on street and action history.
        """
        active = self.active_player
        continue_cost = self.pips[1 - active] - self.pips[active]

        if continue_cost == 0:
            # Player can check.
            # Player can raise if both have remaining chips.
            actions = {CheckAction}
            if self.stacks[active] > 0 and self.stacks[1 - active] > 0:
                actions.add(RaiseAction)
            return actions
        else:
            # Opponent has bet or raised.
            actions = {FoldAction, CallAction}
            if self.stacks[active] > continue_cost and self.stacks[1 - active] > 0:
                actions.add(RaiseAction)
            return actions

    def raise_bounds(self):
        """
        Returns (min_raise, max_raise) as total street pips for the active player.
        """
        active = self.active_player
        continue_cost = self.pips[1 - active] - self.pips[active]
        max_raise = self.pips[active] + self.stacks[active]
        max_raise = min(max_raise, self.pips[1 - active] + self.stacks[1 - active])

        if self.pips[1 - active] == 0:
            min_raise = BIG_BLIND
        else:
            min_raise = self.pips[1 - active] + max(continue_cost, BIG_BLIND)

        min_raise = min(min_raise, max_raise)
        return min_raise, max_raise

    @property
    def active_player(self):
        """
        Determines whose turn it is to act.
        Preflop: Button acts first (pips [1, 2]).
        Postflop: Non-button (Big Blind) acts first.
        """
        if self.street == 0:
            # Preflop: button acted first if initial blinds, or alternates
            if self.previous_state is None:
                return self.button
            prev_active = self.previous_state.active_player
            return 1 - prev_active
        else:
            # Postflop: non-button acts first at start of street
            if self.previous_state is None or self.previous_state.street != self.street:
                return 1 - self.button
            prev_active = self.previous_state.active_player
            return 1 - prev_active

    @property
    def pot(self):
        """
        Total chips currently in the pot.
        Starting stack is 200 each, pot = (200 - stacks[0]) + (200 - stacks[1])
        """
        return (STARTING_STACK - self.stacks[0]) + (STARTING_STACK - self.stacks[1])

    @property
    def pot_odds(self):
        """
        Pot odds = continue_cost / (pot + continue_cost)
        """
        active = self.active_player
        continue_cost = self.pips[1 - active] - self.pips[active]
        if continue_cost <= 0:
            return 0.0
        return continue_cost / (self.pot + continue_cost)
