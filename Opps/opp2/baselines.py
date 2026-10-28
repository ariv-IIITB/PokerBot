"""
baselines.py - Standard benchmark opponents for duplicate-deal validation.
"""

from typing import Any, Dict, Tuple
from evaluator import card_from_str
from preflop import cards_to_canonical


class CheckFoldBot:
    def on_hand_start(self, *args, **kwargs): pass
    def get_action(self, state: Dict[str, Any]) -> Tuple[str, int]:
        legal = state.get("legal_actions", ["check", "fold"])
        return ("check", 0) if "check" in legal else ("fold", 0)
    def on_hand_end(self, *args, **kwargs): pass


class CallingStationBot:
    def on_hand_start(self, *args, **kwargs): pass
    def get_action(self, state: Dict[str, Any]) -> Tuple[str, int]:
        legal = state.get("legal_actions", ["call", "check", "fold"])
        if "call" in legal:
            return ("call", 0)
        return ("check", 0) if "check" in legal else ("fold", 0)
    def on_hand_end(self, *args, **kwargs): pass


class AllInManiacBot:
    def on_hand_start(self, *args, **kwargs): pass
    def get_action(self, state: Dict[str, Any]) -> Tuple[str, int]:
        legal = state.get("legal_actions", ["raise", "call", "fold"])
        max_raise = state.get("max_raise", 0)
        if "raise" in legal and max_raise > 0:
            return ("raise", max_raise)
        if "call" in legal:
            return ("call", 0)
        return ("check", 0) if "check" in legal else ("fold", 0)
    def on_hand_end(self, *args, **kwargs): pass


class NitTagBot:
    def __init__(self):
        self.hole_cards = []

    def on_hand_start(self, hand_id, cards, is_button, *args, **kwargs):
        self.hole_cards = [card_from_str(c) for c in cards]

    def get_action(self, state: Dict[str, Any]) -> Tuple[str, int]:
        legal = state.get("legal_actions", ["check", "fold"])
        street = state.get("street", "preflop")
        min_raise = state.get("min_raise", 0)
        max_raise = state.get("max_raise", 0)
        call_cost = state.get("call_cost", 0)

        _, canonical = cards_to_canonical(self.hole_cards[0], self.hole_cards[1])
        is_premium = canonical in ["AA", "KK", "QQ", "JJ", "TT", "AKs", "AKo", "AQs"]

        if street == "preflop":
            if is_premium:
                if "raise" in legal:
                    return ("raise", int(min(max_raise, min_raise * 2 + 2)))
                return ("call", 0)
            if call_cost == 0:
                return ("check", 0)
            return ("fold", 0)

        if call_cost > 0:
            if is_premium and call_cost <= 10:
                return ("call", 0)
            return ("fold", 0)
        return ("check", 0)

    def on_hand_end(self, *args, **kwargs): pass
