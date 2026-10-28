"""
meta_controller.py - Tournament match-win lock detector and risk management.
"""

from typing import Tuple


class MetaController:
    def __init__(self, total_hands: int = 400, sb: int = 1, bb: int = 2):
        self.total_hands = total_hands
        self.sb = sb
        self.bb = bb

    def compute_lock_status(
        self,
        hand_num: int,
        hero_stack: int,
        opp_stack: int,
        initial_stack: int = 200,
    ) -> Tuple[bool, str]:
        hands_remaining = max(0, self.total_hands - hand_num + 1)
        if hands_remaining == 0:
            return (hero_stack > opp_stack, "TERMINAL")

        bb_hands = (hands_remaining + 1) // 2
        sb_hands = hands_remaining // 2
        max_blind_bleed = bb_hands * self.bb + sb_hands * self.sb
        net_lead = hero_stack - opp_stack

        if net_lead > (max_blind_bleed * 2 + 4):
            return True, "LOCK_MODE"

        return False, "ACTIVE"

    def get_risk_aversion_factor(
        self,
        hand_num: int,
        hero_stack: int,
        opp_stack: int,
    ) -> float:
        hands_remaining = max(1, self.total_hands - hand_num + 1)
        lead = hero_stack - opp_stack
        std_dev = self.bb * 12.0 * (hands_remaining ** 0.5)
        z = lead / max(1.0, std_dev)

        if z > 1.2:
            return 0.05
        elif z < -1.5 and hands_remaining < 90:
            return -0.06
        return 0.0
