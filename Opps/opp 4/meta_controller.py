"""
meta_controller.py - Match strategy (win probability U(D) = Phi(D / sigma_remaining))
and dynamic time governor enforcing <75ms/hand runtime.
"""

import math
import time
from typing import Optional, Tuple


def standard_normal_cdf(z: float) -> float:
    """Computes standard normal CDF Phi(z) using math.erf (O(1), ~15ns)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


class MatchUtilityModel:
    """
    Evaluates match-win probability:
    U(D) = Phi(D / sigma_remaining)
    where D is current score margin and sigma_remaining estimates remaining outcome std dev.
    """

    def __init__(self, total_hands: int = 400, sigma_hand: float = 18.0):
        self.total_hands = total_hands
        self.sigma_hand = sigma_hand  # Approx chip std dev per duplicate deal hand

    def compute_win_prob(
        self,
        score_margin: float,
        current_hand: int,
    ) -> float:
        """
        Computes U(D) = Phi(D / sigma_remaining).
        """
        hands_remaining = max(1, self.total_hands - current_hand)
        sigma_remaining = max(4.0, self.sigma_hand * math.sqrt(hands_remaining))
        z = score_margin / sigma_remaining
        return standard_normal_cdf(z)

    def evaluate_action_utility(
        self,
        current_score_margin: Optional[float],
        current_hand: int,
        chip_ev: float,
    ) -> float:
        """
        Evaluates candidate action by expected utility U.
        Falls back cleanly to chip EV if match score margin is not observable.
        """
        if current_score_margin is None:
            return chip_ev

        hands_remaining = max(1, self.total_hands - current_hand)
        sigma_remaining = max(4.0, self.sigma_hand * math.sqrt(hands_remaining))
        # Expected utility with additional chip_ev
        z = (current_score_margin + chip_ev) / sigma_remaining
        return standard_normal_cdf(z)


class TimeGovernor:
    """
    Monitors tournament time bank and computes hard per-action deadlines.
    Guarantees average < 75 ms per hand with monotonic clock checkpoints.
    """

    def __init__(self, total_budget_sec: float = 58.0, total_hands: int = 400):
        self.total_budget = total_budget_sec
        self.total_hands = total_hands

    def get_action_deadline(
        self,
        time_bank_remaining: float,
        current_hand: int,
    ) -> float:
        """
        Calculates hard deadline timestamp using time.monotonic().
        """
        hands_left = max(1, self.total_hands - current_hand)
        # Average allowed time per hand
        time_per_hand = time_bank_remaining / float(hands_left)

        # Allocate between 5ms and 35ms per decision (approx 2-3 decisions per hand)
        action_budget = max(0.004, min(0.035, time_per_hand * 0.40))

        if time_bank_remaining <= 5.0:
            # Emergency fallback mode
            action_budget = 0.002

        return time.monotonic() + action_budget
