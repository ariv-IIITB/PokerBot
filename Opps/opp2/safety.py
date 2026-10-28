"""
safety.py - Time-bank management and zero-crash action validation.
"""

from typing import Sequence, Tuple
import numpy as np


class TimeGovernor:
    def __init__(self, total_budget_sec: float = 58.0, total_hands: int = 400):
        self.safe_budget = total_budget_sec
        self.total_hands = total_hands

    def get_tier(self, time_remaining: float, hand_num: int) -> str:
        hands_left = max(1, self.total_hands - hand_num + 1)
        ms_per_hand = (time_remaining - 2.0) * 1000.0 / hands_left

        if time_remaining < 4.0 or ms_per_hand < 30.0:
            return "PANIC_O1"
        elif ms_per_hand < 75.0:
            return "FAST_MC"
        return "FULL_MC"


class ActionSanitizer:
    @staticmethod
    def sanitize(
        action_type: str,
        amount: int,
        legal_actions: Sequence[str],
        min_raise: int,
        max_raise: int,
        pot: int,
    ) -> Tuple[str, int]:
        if action_type == "raise":
            if "raise" not in legal_actions or min_raise > max_raise:
                action_type = "call" if "call" in legal_actions else "check"
            else:
                amount = int(np.clip(amount, min_raise, max_raise))
                if (max_raise - amount) <= 0.12 * max(1, pot):
                    amount = max_raise
                return ("raise", amount)

        if action_type == "call":
            if "call" in legal_actions:
                return ("call", 0)
            return ("check", 0) if "check" in legal_actions else ("fold", 0)

        if action_type == "check":
            if "check" in legal_actions:
                return ("check", 0)
            return ("fold", 0)

        return ("fold", 0)
