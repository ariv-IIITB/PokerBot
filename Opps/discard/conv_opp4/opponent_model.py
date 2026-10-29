"""
opponent_model.py - Bayesian opponent modeling with exact Beta priors,
confidence-smoothed statistics (c = n / (n + 25)), and range weight updating.
"""

from typing import List, Tuple, Sequence
import numpy as np

from preflop import (
    TOTAL_COMBOS,
    COMBO_LIST,
    COMBO_CANONICAL,
    cards_to_canonical,
)
from evaluator import evaluate_7cards, card_from_str


class BayesianBetaStat:
    """
    Beta-Binomial Bayesian tracker with prior Beta(alpha, beta) and
    confidence factor c = n / (n + 25) for smooth Bayesian shrinkage.
    """

    def __init__(self, alpha: float, beta: float):
        self.alpha_0 = float(alpha)
        self.beta_0 = float(beta)
        self.prior_mean = self.alpha_0 / (self.alpha_0 + self.beta_0)
        self.successes = 0.0
        self.failures = 0.0

    def observe(self, success: bool, weight: float = 1.0) -> None:
        if success:
            self.successes += weight
        else:
            self.failures += weight

    @property
    def n(self) -> float:
        return self.successes + self.failures

    @property
    def posterior_mean(self) -> float:
        total = self.alpha_0 + self.beta_0 + self.n
        return (self.alpha_0 + self.successes) / total

    @property
    def smoothed_mean(self) -> float:
        """Shrinks posterior mean towards prior mean based on sample size: c = n / (n + 25)."""
        n_obs = self.n
        c = n_obs / (n_obs + 25.0)
        return float((1.0 - c) * self.prior_mean + c * self.posterior_mean)


class OpponentModel:
    """
    Maintains Bayesian statistics and range weights w(h) for all 1,326 combos:
    w(h) = w_preflop(h) * prod_i P(a_i | h, street_i, size_i)
    """

    def __init__(self) -> None:
        # Initial priors as specified in prompt:
        # VPIP: Beta(2, 2)
        # PFR: Beta(1, 3)
        # Fold to Bet: Beta(4, 6)
        # Fold to C-bet: Beta(3, 7)
        self.vpip = BayesianBetaStat(2.0, 2.0)
        self.pfr = BayesianBetaStat(1.0, 3.0)
        self.fold_to_bet = BayesianBetaStat(4.0, 6.0)
        self.fold_to_cbet = BayesianBetaStat(3.0, 7.0)

        # Aggression tracking: (Bets + Raises) / (Bets + Raises + Calls + Checks)
        self.agg_bets_raises = 0.0
        self.agg_total_actions = 0.0

        self.hands_observed = 0

    @property
    def aggression_freq(self) -> float:
        if self.agg_total_actions == 0:
            return 0.35
        c = self.agg_total_actions / (self.agg_total_actions + 25.0)
        sample_af = self.agg_bets_raises / self.agg_total_actions
        return float((1.0 - c) * 0.35 + c * sample_af)

    def observe_action(
        self,
        street: str,
        action: str,
        facing_bet: bool,
        is_cbet_opportunity: bool = False,
    ) -> None:
        """Updates Bayesian stats based on opponent's action."""
        self.agg_total_actions += 1.0
        if action in ("raise", "bet"):
            self.agg_bets_raises += 1.0

        if street == "preflop":
            if action in ("call", "raise"):
                self.vpip.observe(True)
            elif action == "fold":
                self.vpip.observe(False)

            if action == "raise":
                self.pfr.observe(True)
            elif action in ("call", "check", "fold"):
                self.pfr.observe(False)
        else:
            if facing_bet:
                did_fold = (action == "fold")
                self.fold_to_bet.observe(did_fold)
                if is_cbet_opportunity:
                    self.fold_to_cbet.observe(did_fold)

    def get_initial_villain_weights(self) -> np.ndarray:
        """Returns uniform starting weights for all 1,326 combos."""
        return np.ones(TOTAL_COMBOS, dtype=np.float64)

    def update_weights_for_action(
        self,
        weights: np.ndarray,
        action: str,
        board: Sequence[int],
        bet_size: int,
        pot: int,
        dead: Sequence[int] = (),
    ) -> np.ndarray:
        """
        Updates weights w(h) for all 1,326 combos given an observed action.
        Uses exact multipliers:
        Raise: weak/middling/strong = 0.15 / 0.6 / 2.4
        Call:  weak/middling/strong = 0.25 / 0.9 / 1.5
        Check: weak/middling/strong = 1.2  / 1.0 / 0.4
        Strong draws receive a separate bonus.
        """
        updated = weights.copy()
        if len(board) < 3:
            # Preflop updates
            if action == "raise":
                for i in range(TOTAL_COMBOS):
                    canonical = COMBO_CANONICAL[i]
                    # Strong broadway/pair
                    if canonical in ("AA", "KK", "QQ", "JJ", "TT", "AKs", "AKo", "AQs"):
                        updated[i] *= 2.4
                    elif canonical[0] in "AKQJT" or canonical.endswith("s"):
                        updated[i] *= 0.6
                    else:
                        updated[i] *= 0.15
            elif action == "call":
                for i in range(TOTAL_COMBOS):
                    canonical = COMBO_CANONICAL[i]
                    if canonical in ("AA", "KK", "QQ"):
                        updated[i] *= 0.9  # trapping or capped
                    elif canonical[0] in "AKQJT98" or canonical.endswith("s"):
                        updated[i] *= 1.5
                    else:
                        updated[i] *= 0.25
            return updated

        # Postflop updates based on hand texture and category
        board_cards = list(board)
        b_ranks = [c >> 2 for c in board_cards]
        b_suits = [c & 3 for c in board_cards]

        for i in range(TOTAL_COMBOS):
            if updated[i] <= 1e-7:
                continue

            c1, c2 = COMBO_LIST[i]
            # If combo collides with board (or a discarded card), zero it out
            if c1 in board_cards or c2 in board_cards or c1 in dead or c2 in dead:
                updated[i] = 0.0
                continue

            r1, s1 = c1 >> 2, c1 & 3
            r2, s2 = c2 >> 2, c2 & 3

            # Check strong draw: flush draw (4 to a flush) or open-ended straight draw
            suit_match = (
                b_suits.count(s1) >= 2 if s1 == s2 else (
                    b_suits.count(s1) >= 3 or b_suits.count(s2) >= 3
                )
            )
            is_strong_draw = suit_match

            # Hand category on this board
            # Pad board to 5 cards if flop/turn for quick evaluation
            eval_board = board_cards + [c for c in (0, 1, 2, 3) if c not in board_cards and c not in (c1, c2)][:5 - len(board_cards)]
            score = evaluate_7cards([c1, c2] + eval_board)
            cat = score >> 20

            # Classify into weak (0), middling (1), strong (2)
            if cat >= 2:  # Two pair, trips, straight, flush, full house, quads
                strength = 2
            elif cat == 1:  # One pair
                pair_rank = (score & 0xFFFFF) // 2197
                if pair_rank >= max(b_ranks):  # Top pair
                    strength = 2 if (r1 >= 10 or r2 >= 10) else 1
                else:  # Second pair / low pair
                    strength = 1
            else:
                strength = 1 if is_strong_draw else 0

            # Apply multipliers
            if action in ("raise", "bet"):
                mult = 2.4 if strength == 2 else (0.6 if strength == 1 else 0.15)
                if is_strong_draw:
                    mult *= 1.8
            elif action == "call":
                mult = 1.5 if strength >= 1 else 0.25
                if is_strong_draw:
                    mult *= 1.5
            elif action == "check":
                mult = 0.4 if strength == 2 else (1.0 if strength == 1 else 1.2)
            else:
                mult = 1.0

            updated[i] *= mult

        return updated

    def apply_discard(
        self,
        weights: np.ndarray,
        flop: Sequence[int],
        opp_discard: int,
        dead: Sequence[int],
    ) -> np.ndarray:
        """
        The opponent discarded `opp_discard` after seeing the flop and kept the other two.
        Discarded cards are out of play: every combo holding one gets weight 0. A combo
        (a, b) is also unlikely if keeping (a, discard) or (b, discard) would have made a
        stronger hand on this flop (x0.2): a player keeps the best two of three.
        """
        updated = weights.copy()
        flop_cards = list(flop)
        # strength of keeping (c, discard) for every card c, computed once
        with_discard = {
            c: evaluate_7cards([c, opp_discard] + flop_cards)
            for c in range(52) if c not in flop_cards and c != opp_discard
        }
        for i in range(TOTAL_COMBOS):
            if updated[i] <= 1e-7:
                continue
            c1, c2 = COMBO_LIST[i]
            if c1 in dead or c2 in dead or c1 in flop_cards or c2 in flop_cards:
                updated[i] = 0.0
                continue
            kept = evaluate_7cards([c1, c2] + flop_cards)
            if max(with_discard[c1], with_discard[c2]) > kept:
                updated[i] *= 0.2
        return updated
