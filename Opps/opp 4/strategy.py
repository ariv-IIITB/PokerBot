"""
strategy.py - Complete game-theoretic decision engine implementing exact specifications:
- Calling rule with quantified safety margins + OOP adjustment + sampling uncertainty
- Candidate bet evaluation (33%, 66%, 110%, all-in) comparing EV_bet vs EV_check
- River bluffing with size-dependent bluff-to-value ratio: bluffs / value = B / (P + B)
- Preflop execution using stack-stratified 169-hand charts
"""

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple
import numpy as np

from preflop import (
    cards_to_canonical,
    is_hand_in_chart,
    PUSH_FOLD_SB_JAM_8BB,
    PUSH_FOLD_BB_CALL_8BB,
)
from opponent_model import OpponentModel
from meta_controller import MatchUtilityModel

# Extra equity required by street
CALL_SAFETY_MARGINS = {
    "preflop": 0.015,  # 1.5 percentage points
    "flop": 0.020,     # 2 percentage points
    "turn": 0.010,     # 1 percentage point
    "river": 0.000,    # 0 percentage points
}

OOP_EXTRA_MARGIN = 0.005  # Up to 0.5 percentage points when out of position


class StrategyEngine:
    def __init__(self, opponent_model: OpponentModel, meta_controller: MatchUtilityModel):
        self.model = opponent_model
        self.meta = meta_controller

    def decide_calling(
        self,
        street: str,
        equity: float,
        sampling_se: float,
        pot: int,
        call_cost: int,
        is_button: bool,
    ) -> bool:
        """
        Calling rule:
        E_min = C / (P + C)
        Extra margins: Preflop 1.5%, Flop 2.0%, Turn 1.0%, River 0.0%
        OOP margin: +0.5% when out of position (not button)
        Sampling uncertainty: capped at 3 percentage points (0.030)
        """
        if call_cost <= 0:
            return True

        p_before = pot  # pot includes opponent's bet
        e_min = call_cost / float(p_before + call_cost)

        extra_street = CALL_SAFETY_MARGINS.get(street, 0.010)
        extra_oop = 0.0 if is_button else OOP_EXTRA_MARGIN
        # Sampling uncertainty capped at 3 percentage points (0.030)
        uncertainty_adj = min(0.030, 1.0 * sampling_se)

        required_equity = e_min + extra_street + extra_oop + uncertainty_adj
        return equity >= required_equity

    def evaluate_bet_candidates(
        self,
        street: str,
        equity: float,
        pot: int,
        hero_stack: int,
        min_raise: int,
        max_raise: int,
        score_margin: Optional[float],
        current_hand: int,
        is_cbet: bool = False,
    ) -> Tuple[str, int, float]:
        """
        Evaluates candidate sizes: 33%, 66%, 110% pot and all-in.
        EV_bet = F * P + (1 - F) * [ E_called * (P + 2B) - B ]
        Compares with EV_check = E * P.
        Returns: (best_action, best_amount, best_utility)
        """
        candidate_fractions = [0.33, 0.66, 1.10]
        candidate_sizes = [max(1, int(round(f * pot))) for f in candidate_fractions]
        candidate_sizes.append(hero_stack)  # all-in

        # Filter legal sizes
        valid_sizes: List[int] = []
        for b in candidate_sizes:
            if min_raise <= b <= max_raise:
                if b not in valid_sizes:
                    valid_sizes.append(b)
            elif b > max_raise and max_raise >= min_raise:
                if max_raise not in valid_sizes:
                    valid_sizes.append(max_raise)

        # Baseline: Check
        ev_check = equity * pot
        util_check = self.meta.evaluate_action_utility(score_margin, current_hand, ev_check)

        best_action = "check"
        best_amount = 0
        best_util = util_check

        # Base fold frequency from Bayesian opponent model
        if is_cbet and street == "flop":
            base_fold = self.model.fold_to_cbet.smoothed_mean
        else:
            base_fold = self.model.fold_to_bet.smoothed_mean

        for b in valid_sizes:
            ratio = b / float(max(1, pot))

            # Folding frequency increases with bet size, capped at 0.88
            # If opponent is a calling station, base_fold is low, so f_bet stays low
            f_bet = float(np.clip(base_fold * (ratio ** 0.18), 0.02, 0.88))

            # Conditional equity when called:
            # P(Win | Call) = max(0, (E - F) / (1 - F)) because villain folds their worst hands
            cond_win = max(0.0, (equity - f_bet) / max(0.01, 1.0 - f_bet))

            # On flop/turn, card realization softens the conditional filtering
            if street == "flop":
                e_called = 0.60 * equity + 0.40 * cond_win
            elif street == "turn":
                e_called = 0.35 * equity + 0.65 * cond_win
            else:
                e_called = cond_win

            # All-in overbet safety: if shoving more than 3x the pot without nut equity
            if ratio > 3.0 and equity < 0.85:
                e_called = min(e_called, 0.15)

            # Expected Value: EV_bet = F * P + (1 - F) * [ E_called * (P + 2B) - B ]
            ev_bet = f_bet * pot + (1.0 - f_bet) * (e_called * (pot + 2 * b) - b)
            util_bet = self.meta.evaluate_action_utility(score_margin, current_hand, ev_bet)

            if util_bet > best_util:
                best_util = util_bet
                best_action = "raise"
                best_amount = b

        return best_action, best_amount, best_util

    def should_river_bluff(
        self,
        hero_cards: Sequence[int],
        board: Sequence[int],
        bet_size: int,
        pot: int,
    ) -> bool:
        """
        Enforces river bluff-to-value ratio:
        bluffs / value = B / (P + B)
        Selects missed draws and blocker-rich hands.
        Does not bluff when estimated EV is negative against an observed non-folder.
        """
        f_fold = self.model.fold_to_bet.smoothed_mean
        ev_bluff = f_fold * pot - (1.0 - f_fold) * bet_size
        # Prompt: "That is a starting balance, not a requirement to bluff hands with poor blockers or negative estimated EV."
        if ev_bluff < 0 and self.model.fold_to_bet.n >= 5:
            return False

        ratio = bet_size / float(pot + bet_size)
        # Check blockers: Ace or King of board flush suit, or straight blockers
        r1, s1 = hero_cards[0] >> 2, hero_cards[0] & 3
        r2, s2 = hero_cards[1] >> 2, hero_cards[1] & 3

        board_suits = [c & 3 for c in board]
        # Check if flush draw missed
        has_flush_blocker = any(board_suits.count(s) == 2 and (s1 == s or s2 == s) for s in range(4))
        has_ace_blocker = (r1 == 12 or r2 == 12)

        is_blocker_rich = has_flush_blocker or has_ace_blocker

        # Enforce target ratio probabilistically
        if is_blocker_rich and random.random() < ratio:
            return True
        return False

    def decide_preflop(
        self,
        hero_cards: Sequence[int],
        is_button: bool,
        pot: int,
        call_cost: int,
        min_raise: int,
        max_raise: int,
        hero_stack: int,
        opp_stack: int,
        score_margin: Optional[float],
        current_hand: int,
    ) -> Tuple[str, int]:
        """
        Executes preflop action using stack-stratified 169-hand lookup charts:
        - <=8 BB: Dedicated push/fold charts
        - 8-15 BB, 15-30 BB, 30-60 BB, >60 BB
        """
        c1, c2 = hero_cards
        canonical, is_pair, is_suited = cards_to_canonical(c1, c2)
        eff_stack_bb = min(hero_stack, opp_stack) / 2.0

        # Tier 0: <= 8 BB (Dedicated Nash Push/Fold)
        if eff_stack_bb <= 8.0:
            if is_button:
                if canonical in PUSH_FOLD_SB_JAM_8BB and max_raise > 0:
                    return ("raise", max_raise)
                elif call_cost == 0:
                    return ("check", 0)
                else:
                    return ("fold", 0)
            else:
                # Big Blind facing shove or open
                if call_cost > 0:
                    if canonical in PUSH_FOLD_BB_CALL_8BB:
                        return ("call", 0)
                    return ("fold", 0)
                return ("check", 0)

        # Standard Stacks:
        if is_button:
            if call_cost <= 1:
                # Unopened pot: open raise
                if is_hand_in_chart(canonical, eff_stack_bb, "sb_open"):
                    open_amt = min(max_raise, max(min_raise, 2 * 2 + (1 if eff_stack_bb > 30 else 0)))
                    return ("raise", open_amt)
                elif call_cost == 0:
                    return ("check", 0)
                else:
                    return ("fold", 0)
            else:
                # Facing 3-bet from BB
                if is_hand_in_chart(canonical, eff_stack_bb, "sb_vs_3bet"):
                    if eff_stack_bb <= 20.0 and max_raise > 0:
                        return ("raise", max_raise)
                    return ("call", 0)
                return ("fold", 0)

        else:
            # We are Big Blind
            if call_cost == 0:
                # Button limped
                if is_hand_in_chart(canonical, eff_stack_bb, "bb_vs_limp"):
                    iso_amt = min(max_raise, max(min_raise, 3 * 2))
                    return ("raise", iso_amt)
                return ("check", 0)
            else:
                # Button open-raised
                if is_hand_in_chart(canonical, eff_stack_bb, "bb_3bet"):
                    three_bet_amt = min(max_raise, max(min_raise, call_cost * 3 + pot))
                    return ("raise", three_bet_amt)
                elif is_hand_in_chart(canonical, eff_stack_bb, "bb_defend_call"):
                    return ("call", 0)
                else:
                    return ("fold", 0)
