"""
baselines.py - Standard benchmark opponents for duplicate-deal validation:
- CallingStationBot (passive calling)
- CheckFoldBot (passive folding)
- AllInManiacBot (aggressive shoving)
- NitTagBot (basic heuristic)
- RandomBot (random action selection)
"""

import random
from typing import Any, Dict, Sequence, Tuple
from evaluator import card_from_str
from preflop import cards_to_canonical


class CallingStationBot:
    """Never folds; calls every bet, checks when free."""
    def on_hand_start(self, *args, **kwargs): pass
    def on_hand_end(self, *args, **kwargs): pass
    def get_action(self, state: Dict[str, Any]) -> Tuple[str, int]:
        legal = state.get("legal_actions", ["call", "check", "fold"])
        if "call" in legal:
            return ("call", 0)
        return ("check", 0) if "check" in legal else ("fold", 0)


class CheckFoldBot:
    """Extreme nit: checks if free, otherwise folds immediately."""
    def on_hand_start(self, *args, **kwargs): pass
    def on_hand_end(self, *args, **kwargs): pass
    def get_action(self, state: Dict[str, Any]) -> Tuple[str, int]:
        legal = state.get("legal_actions", ["check", "fold"])
        return ("check", 0) if "check" in legal else ("fold", 0)


class AllInManiacBot:
    """Shoves all-in whenever possible; otherwise calls or checks."""
    def on_hand_start(self, *args, **kwargs): pass
    def on_hand_end(self, *args, **kwargs): pass
    def get_action(self, state: Dict[str, Any]) -> Tuple[str, int]:
        legal = state.get("legal_actions", ["raise", "call", "fold"])
        max_raise = state.get("max_raise", 0)
        if "raise" in legal and max_raise > 0:
            return ("raise", max_raise)
        if "call" in legal:
            return ("call", 0)
        return ("check", 0) if "check" in legal else ("fold", 0)


class RandomBot:
    """Random choice among legal actions with random bet sizing."""
    def on_hand_start(self, *args, **kwargs): pass
    def on_hand_end(self, *args, **kwargs): pass
    def get_action(self, state: Dict[str, Any]) -> Tuple[str, int]:
        legal = state.get("legal_actions", ["check", "fold"])
        act = random.choice(legal)
        if act == "raise":
            min_r = state.get("min_raise", 4)
            max_r = state.get("max_raise", 200)
            amt = random.randint(min_r, max(min_r, max_r))
            return ("raise", amt)
        return (act, 0)


class NitTagBot:
    """Heuristic bot: raises premium preflop, bets top pair+ postflop, folds weak hands."""
    def __init__(self):
        self.hole_cards = []

    def on_hand_start(self, hand_id, cards, is_button, *args, **kwargs):
        self.hole_cards = [card_from_str(c) for c in cards]

    def on_hand_end(self, *args, **kwargs): pass

    def get_action(self, state: Dict[str, Any]) -> Tuple[str, int]:
        legal = state.get("legal_actions", ["check", "fold"])
        street = state.get("street", "preflop")
        min_raise = state.get("min_raise", 0)
        max_raise = state.get("max_raise", 0)
        call_cost = state.get("call_cost", 0)

        canonical, _, _ = cards_to_canonical(self.hole_cards[0], self.hole_cards[1])
        is_premium = canonical in ["AA", "KK", "QQ", "JJ", "TT", "AKs", "AKo", "AQs"]

        if street == "preflop":
            if is_premium:
                if "raise" in legal and max_raise >= min_raise:
                    return ("raise", min(max_raise, max(min_raise, 6)))
                return ("call", 0)
            if call_cost == 0:
                return ("check", 0)
            return ("fold", 0)

        # Postflop
        if call_cost > 0:
            if is_premium and call_cost <= 10 and "call" in legal:
                return ("call", 0)
            return ("fold", 0)

        if is_premium and "raise" in legal and max_raise >= min_raise:
            pot = state.get("pot", 10)
            return ("raise", min(max_raise, max(min_raise, pot // 2)))
        return ("check", 0)
