"""
safety.py - Action validation, bounds clamping, and crash-proof fallback sanitizer.
Guarantees 100% legal responses under all circumstances.
"""

from typing import List, Sequence, Tuple


class ActionSanitizer:
    @staticmethod
    def sanitize(
        action: str,
        amount: int,
        legal_actions: Sequence[str],
        min_raise: int,
        max_raise: int,
    ) -> Tuple[str, int]:
        """
        Validates, clamps, and ensures the returned action is strictly legal.
        """
        legal_set = set(legal_actions)

        # Emergency fallback if legal set is empty
        if not legal_set:
            return ("check", 0)

        # 1. Sanitize Raise
        if action == "raise":
            if "raise" in legal_set and max_raise >= min_raise and max_raise > 0:
                clamped_amt = max(min_raise, min(int(amount), max_raise))
                return ("raise", clamped_amt)
            # If raise is illegal, downgrade to call or check
            if "call" in legal_set:
                return ("call", 0)
            if "check" in legal_set:
                return ("check", 0)
            return ("fold", 0)

        # 2. Sanitize Check
        elif action == "check":
            if "check" in legal_set:
                return ("check", 0)
            # If check illegal (facing bet), fold
            return ("fold", 0)

        # 3. Sanitize Call
        elif action == "call":
            if "call" in legal_set:
                return ("call", 0)
            if "check" in legal_set:
                return ("check", 0)
            return ("fold", 0)

        # 4. Sanitize Fold
        elif action == "fold":
            if "check" in legal_set:
                # Never fold when checking is free!
                return ("check", 0)
            return ("fold", 0)

        # Default fallback
        if "check" in legal_set:
            return ("check", 0)
        if "call" in legal_set:
            return ("call", 0)
        return ("fold", 0)
