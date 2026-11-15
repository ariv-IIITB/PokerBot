"""
Baseline bots for heads-up pokerbot evaluation.
Includes:
- AlwaysCallBot: Calling station that never folds and checks when possible.
- AlwaysFoldBot: Folds immediately facing any raise/bet.
- RandomBot: Uniform random choice among legal actions.
- TightBot: Conservative value-only player.
"""

import random
from skeleton.main_bot import Bot
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction
from skeleton.evaluate import get_preflop_equity, estimate_equity


class AlwaysCallBot(Bot):
    """The quintessential calling station: checks when free, calls every bet."""

    def handle_new_round(self, game_state, round_state, active):
        pass

    def handle_round_over(self, game_state, terminal_state, active):
        pass

    def get_action(self, game_state, round_state, active):
        legal = round_state.legal_actions()
        if CheckAction in legal:
            return CheckAction()
        return CallAction()


class AlwaysFoldBot(Bot):
    """Extreme nit: checks if free, otherwise immediately folds."""

    def handle_new_round(self, game_state, round_state, active):
        pass

    def handle_round_over(self, game_state, terminal_state, active):
        pass

    def get_action(self, game_state, round_state, active):
        legal = round_state.legal_actions()
        if CheckAction in legal:
            return CheckAction()
        return FoldAction()


class RandomBot(Bot):
    """Plays randomly among legal actions with random raise sizing."""

    def handle_new_round(self, game_state, round_state, active):
        pass

    def handle_round_over(self, game_state, terminal_state, active):
        pass

    def get_action(self, game_state, round_state, active):
        legal = list(round_state.legal_actions())
        chosen_cls = random.choice(legal)
        if chosen_cls == RaiseAction:
            min_raise, max_raise = round_state.raise_bounds()
            if min_raise < max_raise:
                amt = random.randint(min_raise, max_raise)
            else:
                amt = min_raise
            return RaiseAction(amt)
        return chosen_cls()


class TightBot(Bot):
    """
    Conservative tight-passive/tight-aggressive bot.
    Plays top 35% hands preflop, bets top pair+ postflop, folds marginal hands to raises.
    """

    def handle_new_round(self, game_state, round_state, active):
        pass

    def handle_round_over(self, game_state, terminal_state, active):
        pass

    def get_action(self, game_state, round_state, active):
        my_cards = round_state.hands[active]
        board = round_state.deck
        legal = round_state.legal_actions()
        continue_cost = round_state.pips[1 - active] - round_state.pips[active]

        if round_state.street == 0:
            # Preflop
            eq = get_preflop_equity(my_cards[0], my_cards[1])
            if eq < 0.45:
                # Fold junk
                return CheckAction() if CheckAction in legal else FoldAction()
            elif eq > 0.65:
                # Raise premium
                if RaiseAction in legal:
                    min_r, max_r = round_state.raise_bounds()
                    pot = round_state.pot
                    amt = min(max_r, max(min_r, round_state.pips[active] + pot // 2))
                    return RaiseAction(amt)
                return CallAction() if CallAction in legal else CheckAction()
            else:
                # Call / check playable hands
                return CheckAction() if CheckAction in legal else CallAction()
        else:
            # Postflop
            eq = estimate_equity(my_cards, board, n_samples=150, time_budget=0.02)
            pot = round_state.pot
            pot_odds = round_state.pot_odds

            if eq > 0.65:
                # Bet/raise for value
                if RaiseAction in legal:
                    min_r, max_r = round_state.raise_bounds()
                    target_bet = round_state.pips[active] + max(4, pot // 2)
                    amt = min(max_r, max(min_r, target_bet))
                    return RaiseAction(amt)
                return CallAction() if CallAction in legal else CheckAction()
            elif eq >= pot_odds and eq > 0.40:
                # Call with decent equity
                return CheckAction() if CheckAction in legal else CallAction()
            else:
                # Fold when behind
                return CheckAction() if CheckAction in legal else FoldAction()
