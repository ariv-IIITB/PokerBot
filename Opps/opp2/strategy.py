"""
strategy.py - Core game-theoretic decision policy with board texture and MDF.
"""

from typing import Sequence, Tuple
import numpy as np
from preflop import cards_to_canonical, should_bb_call_jam, should_sb_jam, SB_OPEN_NAMES
from equity import calculate_equity_mc, calculate_river_exact
from opponent_model import OpponentModel
from meta_controller import MetaController


def classify_board_texture(board: Sequence[int]) -> float:
    if len(board) < 3:
        return 0.0

    ranks = [c >> 2 for c in board]
    suits = [c & 3 for c in board]

    suit_counts = [suits.count(s) for s in range(4)]
    max_suit = max(suit_counts)
    flush_score = 0.45 if max_suit >= 4 else (0.25 if max_suit == 3 else 0.0)

    straight_score = 0.0
    sorted_unique_ranks = sorted(set(ranks))
    for i in range(len(sorted_unique_ranks)):
        for j in range(i + 1, len(sorted_unique_ranks)):
            span = sorted_unique_ranks[j] - sorted_unique_ranks[i]
            if span <= 4:
                straight_score += 0.08
    straight_score = min(0.40, straight_score)
    pair_discount = 0.15 if len(ranks) != len(set(ranks)) else 0.0

    return float(np.clip(flush_score + straight_score - pair_discount, 0.0, 1.0))


class StrategyEngine:
    def __init__(self, opponent_model: OpponentModel, meta_controller: MetaController):
        self.model = opponent_model
        self.meta = meta_controller

    def decide_preflop(
        self,
        hero_cards: Sequence[int],
        button: bool,
        pot: int,
        call_cost: int,
        min_raise: int,
        max_raise: int,
        hero_stack: int,
        opp_stack: int,
        hand_num: int,
    ) -> Tuple[str, int]:
        c1, c2 = hero_cards
        _, canonical = cards_to_canonical(c1, c2)
        eff_stack_bb = min(hero_stack, opp_stack) / 2.0

        if eff_stack_bb <= 14.0:
            if button:
                if should_sb_jam(canonical, eff_stack_bb):
                    return ("raise", max_raise)
                elif call_cost == 0:
                    return ("check", 0)
                else:
                    return ("fold", 0)
            else:
                if call_cost > 0 and call_cost >= (hero_stack - 2):
                    if should_bb_call_jam(canonical, eff_stack_bb):
                        return ("call", call_cost)
                    return ("fold", 0)

        if button:
            if call_cost <= 1:
                if canonical in SB_OPEN_NAMES:
                    open_size = int(np.clip(pot * 2 + 1, min_raise, max_raise))
                    return ("raise", open_size)
                return ("fold", 0)
            else:
                if canonical in ["AA", "KK", "QQ", "JJ", "AKs", "AKo"]:
                    return ("raise", max_raise)
                pot_odds = call_cost / (pot + call_cost)
                if pot_odds < 0.32:
                    return ("call", call_cost)
                return ("fold", 0)
        else:
            if call_cost == 0:
                return ("check", 0)
            pot_odds = call_cost / (pot + call_cost)
            if call_cost <= 4:
                if canonical in ["AA", "KK", "QQ", "JJ", "AKs", "A5s", "A4s", "KQs"]:
                    three_bet = int(np.clip(call_cost * 3 + pot, min_raise, max_raise))
                    return ("raise", three_bet)
                if pot_odds <= 0.40:
                    return ("call", call_cost)
                return ("fold", 0)
            else:
                if should_bb_call_jam(canonical, eff_stack_bb):
                    return ("call", call_cost)
                return ("fold", 0)

    def decide_postflop(
        self,
        street: str,
        hero_cards: Sequence[int],
        board: Sequence[int],
        button: bool,
        pot: int,
        call_cost: int,
        min_raise: int,
        max_raise: int,
        hero_stack: int,
        opp_stack: int,
        villain_weights: np.ndarray,
        compute_tier: str = "FULL_MC",
        hand_num: int = 1,
    ) -> Tuple[str, int]:
        eff_stack = min(hero_stack, opp_stack)
        texture = classify_board_texture(board)
        gamma = self.meta.get_risk_aversion_factor(hand_num, hero_stack, opp_stack)

        if street == "river" or compute_tier == "PANIC_O1":
            equity = calculate_river_exact(hero_cards, board, villain_weights)
            ppot = 0.0
            ehs = equity
        else:
            n_rolls = 180 if compute_tier == "FAST_MC" else 380
            equity, ppot, ehs = calculate_equity_mc(
                hero_cards, board, villain_weights, n_rollouts=n_rolls
            )

        pos_multiplier = 1.05 if button else 0.92
        realized_eq = float(np.clip(equity * pos_multiplier, 0.0, 1.0))

        if call_cost > 0:
            pot_odds = call_cost / (pot + call_cost)
            required_eq = pot_odds + gamma

            if ehs >= 0.88 or (equity >= 0.78 and call_cost < eff_stack * 0.4):
                if min_raise <= max_raise:
                    target = int(min(max_raise, pot + call_cost * 2))
                    return ("raise", target)
                return ("call", call_cost)

            if ppot >= 0.28 and call_cost <= pot * 0.5 and min_raise <= max_raise:
                return ("raise", min_raise)

            if realized_eq >= required_eq or (ehs >= 0.52 and call_cost <= pot * 0.4):
                return ("call", call_cost)

            return ("fold", 0)

        else:
            if ehs >= 0.68 or (street == "river" and equity >= 0.65):
                bet_target = int(pot * 0.75) if texture > 0.50 else int(pot * 0.35)
                bet_val = int(np.clip(bet_target, min_raise, max_raise))
                if bet_val > 0 and min_raise <= max_raise:
                    return ("raise", bet_val)
                return ("check", 0)

            if street in ["flop", "turn"] and (ppot >= 0.22 or button):
                if self.model.fold_to_cbet.mean >= 0.48 or ppot >= 0.25:
                    bet_val = int(np.clip(pot * 0.33, min_raise, max_raise))
                    if bet_val > 0 and min_raise <= max_raise:
                        return ("raise", bet_val)

            if street == "river" and equity < 0.25 and self.model.fold_to_river.mean >= 0.52:
                bluff_val = int(np.clip(pot * 0.66, min_raise, max_raise))
                if bluff_val > 0 and min_raise <= max_raise:
                    return ("raise", bluff_val)

            return ("check", 0)
