"""
Abstract Bot base class for Heads-Up No-Limit Texas Hold'em.
"""

from abc import ABC, abstractmethod


class Bot(ABC):
    """
    Base class that any competitive bot must inherit from.
    """

    @abstractmethod
    def handle_new_round(self, game_state, round_state, active):
        """
        Called when a new round starts.
        
        Args:
            game_state: GameState namedtuple containing bankroll, game_clock, round_num.
            round_state: Initial RoundState with hole cards.
            active: Integer index (0 or 1) indicating our seat.
        """
        pass

    @abstractmethod
    def handle_round_over(self, game_state, terminal_state, active):
        """
        Called when a round finishes.
        
        Args:
            game_state: GameState namedtuple with updated bankroll and game_clock.
            terminal_state: TerminalState with deltas and final RoundState.
            active: Integer index (0 or 1) indicating our seat.
        """
        pass

    @abstractmethod
    def get_action(self, game_state, round_state, active):
        """
        Called when it is our turn to act.
        
        Args:
            game_state: GameState namedtuple with bankroll, game_clock, round_num.
            round_state: Current RoundState.
            active: Integer index (0 or 1) indicating our seat.
            
        Returns:
            An instance of FoldAction, CallAction, CheckAction, or RaiseAction.
        """
        pass
