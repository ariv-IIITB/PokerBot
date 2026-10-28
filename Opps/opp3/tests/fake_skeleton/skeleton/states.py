"""Minimal stand-in mirroring the MIT pokerbots skeleton API (for adapter tests only)."""
from collections import namedtuple
from .actions import FoldAction, CallAction, CheckAction, RaiseAction

NUM_ROUNDS = 400
STARTING_STACK = 400
BIG_BLIND = 2
SMALL_BLIND = 1

GameState = namedtuple('GameState', ['bankroll', 'game_clock', 'round_num'])
TerminalState = namedtuple('TerminalState', ['deltas', 'previous_state'])


class RoundState(namedtuple('_RoundState', ['button', 'street', 'pips', 'stacks', 'hands', 'deck', 'previous_state'])):
    def legal_actions(self):
        active = self.button % 2
        continue_cost = self.pips[1 - active] - self.pips[active]
        if continue_cost == 0:
            bets_forbidden = (self.stacks[0] == 0 or self.stacks[1] == 0)
            return {CheckAction} if bets_forbidden else {CheckAction, RaiseAction}
        raises_forbidden = (continue_cost == self.stacks[active] or self.stacks[1 - active] == 0)
        return {FoldAction, CallAction} if raises_forbidden else {FoldAction, CallAction, RaiseAction}

    def raise_bounds(self):
        active = self.button % 2
        continue_cost = self.pips[1 - active] - self.pips[active]
        max_contribution = min(self.stacks[active], self.stacks[1 - active] + continue_cost)
        min_contribution = min(max_contribution, continue_cost + max(continue_cost, BIG_BLIND))
        return (self.pips[active] + min_contribution, self.pips[active] + max_contribution)
