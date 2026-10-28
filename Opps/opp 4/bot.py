"""
bot.py - Tournament-ready PokerBot (Opponent 4) implementing:
- 169-hand stack-stratified preflop charts (with push/fold <=8 BB)
- Range-weighted opponent hole-card sampling (256 preflop, 384 flop, 512 turn, exact river)
- Strict calling rule with quantified safety margins, OOP penalty, and sampling uncertainty
- Candidate bet evaluation (33%, 66%, 110%, all-in) with highest estimated EV / match utility
- River bluffing with size-dependent bluff-to-value ratio: B / (P + B)
- Bayesian opponent tracker: Beta(2,2), Beta(1,3), Beta(4,6), Beta(3,7) with c = n / (n + 25)
- Match-win probability utility: U(D) = Phi(D / sigma_remaining)
- Hard monotonic clock deadlines (<75ms/hand target) and crash-proof safety sanitization
"""

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from evaluator import card_from_str, card_to_str, evaluate_7cards
from preflop import cards_to_canonical, TOTAL_COMBOS
from opponent_model import OpponentModel
from meta_controller import MatchUtilityModel, TimeGovernor
from strategy import StrategyEngine
from safety import ActionSanitizer
from equity import calculate_equity


class PokerBot:
    """
    Opponent 4 Tournament Poker Bot.
    """

    def __init__(self, total_hands: int = 400, time_budget: float = 58.0) -> None:
        self.model = OpponentModel()
        self.meta = MatchUtilityModel(total_hands=total_hands)
        self.governor = TimeGovernor(total_budget_sec=time_budget, total_hands=total_hands)
        self.strategy = StrategyEngine(self.model, self.meta)

        self.hand_num = 0
        self.hero_cards: List[int] = []
        self.is_button = False
        self.hero_stack = 200
        self.opp_stack = 200
        self.cumulative_score_margin = 0.0

        self.villain_weights = self.model.get_initial_villain_weights()
        self.previous_pot = 0
        self.we_were_preflop_aggressor = False

    def on_hand_start(
        self,
        hand_id: int,
        hole_cards_str: Sequence[str],
        is_button: bool,
        hero_stack: int = 200,
        opp_stack: int = 200,
    ) -> None:
        """Called at the start of each new hand."""
        try:
            self.hand_num = hand_id
            self.hero_cards = [card_from_str(c) for c in hole_cards_str]
            self.is_button = is_button
            self.hero_stack = hero_stack
            self.opp_stack = opp_stack
            self.villain_weights = self.model.get_initial_villain_weights()
            self.previous_pot = 0
            self.we_were_preflop_aggressor = False
        except Exception:
            self.hero_cards = [0, 1]

    def on_hand_end(
        self,
        hero_delta: int,
        opp_delta: int,
        showdown_cards: Optional[Sequence[str]] = None,
    ) -> None:
        """Called when a hand concludes."""
        try:
            self.cumulative_score_margin += float(hero_delta)
            self.model.hands_observed += 1
        except Exception:
            pass

    def get_action(self, game_state: Dict[str, Any]) -> Tuple[str, int]:
        """
        Main decision method. Receives game_state dict and returns (action, amount).
        Guaranteed to never raise an unhandled exception and strictly return a legal action.
        """
        legal = game_state.get("legal_actions", ["check", "fold"])
        min_raise = game_state.get("min_raise", 0)
        max_raise = game_state.get("max_raise", 0)
        pot = game_state.get("pot", 3)
        call_cost = game_state.get("call_cost", 0)
        hero_stack = game_state.get("hero_stack", self.hero_stack)
        opp_stack = game_state.get("opp_stack", self.opp_stack)
        time_bank = game_state.get("time_bank", 50.0)
        street = game_state.get("street", "preflop")
        board_str = game_state.get("board", [])

        # Set monotonic clock deadline
        deadline = self.governor.get_action_deadline(time_bank, self.hand_num)

        try:
            board = [card_from_str(c) for c in board_str]

            # 1. PREFLOP
            if street == "preflop":
                act, amt = self.strategy.decide_preflop(
                    self.hero_cards,
                    self.is_button,
                    pot,
                    call_cost,
                    min_raise,
                    max_raise,
                    hero_stack,
                    opp_stack,
                    self.cumulative_score_margin,
                    self.hand_num,
                )
                if act == "raise":
                    self.we_were_preflop_aggressor = True
                return ActionSanitizer.sanitize(act, amt, legal, min_raise, max_raise)

            # 2. POSTFLOP
            # Update opponent combo weights w(h) if pot grew
            if pot > self.previous_pot and self.previous_pot > 0:
                opp_bet = pot - self.previous_pot
                self.villain_weights = self.model.update_weights_for_action(
                    self.villain_weights,
                    "raise" if call_cost > 0 else "check",
                    board,
                    opp_bet,
                    pot,
                )
            self.previous_pot = pot

            # Compute range-weighted equity with specified samples
            equity, se = calculate_equity(
                self.hero_cards,
                board,
                self.villain_weights,
                street,
                deadline=deadline,
            )

            # Facing a bet or raise
            if call_cost > 0:
                # Observe opponent bet in Bayesian model
                self.model.observe_action(street, "raise", facing_bet=True)

                should_call = self.strategy.decide_calling(
                    street,
                    equity,
                    se,
                    pot,
                    call_cost,
                    self.is_button,
                )

                if should_call:
                    # Monster hand re-raise (equity > 0.85)
                    if equity > 0.85 and "raise" in legal and max_raise >= min_raise:
                        raise_amt = min(max_raise, max(min_raise, call_cost * 2 + pot // 2))
                        return ActionSanitizer.sanitize("raise", raise_amt, legal, min_raise, max_raise)
                    return ActionSanitizer.sanitize("call", 0, legal, min_raise, max_raise)
                else:
                    return ActionSanitizer.sanitize("fold", 0, legal, min_raise, max_raise)

            # Uncontested (facing check)
            else:
                is_cbet = (street == "flop" and self.we_were_preflop_aggressor)
                best_act, best_amt, best_util = self.strategy.evaluate_bet_candidates(
                    street,
                    equity,
                    pot,
                    hero_stack,
                    min_raise,
                    max_raise,
                    self.cumulative_score_margin,
                    self.hand_num,
                    is_cbet=is_cbet,
                )

                # Check if river bluff applies on check
                if street == "river" and best_act == "check" and equity < 0.35:
                    bluff_size = max(min_raise, int(round(0.66 * pot)))
                    if min_raise <= bluff_size <= max_raise and "raise" in legal:
                        if self.strategy.should_river_bluff(self.hero_cards, board, bluff_size, pot):
                            return ActionSanitizer.sanitize("raise", bluff_size, legal, min_raise, max_raise)

                return ActionSanitizer.sanitize(best_act, best_amt, legal, min_raise, max_raise)

        except Exception:
            # Emergency crash-proof fallback
            if "check" in legal:
                return ("check", 0)
            if "call" in legal and call_cost <= 2:
                return ("call", 0)
            return ("fold", 0)

    # MIT Pokerbots Skeleton Adapter hooks (for duplicate match engine compatibility)
    def handle_new_round(self, game_state, round_state, active):
        try:
            is_button = (active == round_state.button)
            my_cards = round_state.hands[active]
            h_stack = round_state.stacks[active]
            o_stack = round_state.stacks[1 - active]
            self.on_hand_start(game_state.round_num, my_cards, is_button, h_stack, o_stack)
        except Exception:
            pass

    def handle_round_over(self, game_state, terminal_state, active):
        try:
            delta = terminal_state.deltas[active]
            opp_delta = terminal_state.deltas[1 - active]
            self.on_hand_end(delta, opp_delta)
        except Exception:
            pass
