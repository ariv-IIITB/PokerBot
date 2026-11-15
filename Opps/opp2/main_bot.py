"""
bot.py - Primary tournament bot entrypoint with complete fault tolerance.
"""

from typing import Any, Dict, List, Tuple
from evaluator import card_from_str, evaluate_7cards
from opponent_model import OpponentModel
from meta_controller import MetaController
from strategy import StrategyEngine
from safety import ActionSanitizer, TimeGovernor


class PokerBot:
    def __init__(self) -> None:
        self.model = OpponentModel()
        self.meta = MetaController(total_hands=400, sb=1, bb=2)
        self.strategy = StrategyEngine(self.model, self.meta)
        self.governor = TimeGovernor(total_budget_sec=58.0, total_hands=400)
        self.hand_num = 0
        self.hero_cards: List[int] = []
        self.is_button = False
        self.villain_weights = self.model.get_initial_villain_weights()

    def on_hand_start(
        self,
        hand_id: int,
        hole_cards_str: List[str],
        is_button: bool,
        hero_stack: int,
        opp_stack: int,
    ) -> None:
        try:
            self.hand_num = hand_id
            self.hero_cards = [card_from_str(c) for c in hole_cards_str]
            self.is_button = is_button
            self.villain_weights = self.model.get_initial_villain_weights()
        except Exception:
            self.hero_cards = [0, 1]

    def get_action(self, game_state: Dict[str, Any]) -> Tuple[str, int]:
        legal = game_state.get("legal_actions", ["check", "fold"])
        min_raise = game_state.get("min_raise", 0)
        max_raise = game_state.get("max_raise", 0)
        pot = game_state.get("pot", 3)
        call_cost = game_state.get("call_cost", 0)
        hero_stack = game_state.get("hero_stack", 200)
        opp_stack = game_state.get("opp_stack", 200)
        time_bank = game_state.get("time_bank", 50.0)
        street = game_state.get("street", "preflop")
        board_str = game_state.get("board", [])
        board = [card_from_str(c) for c in board_str]

        is_locked, mode = self.meta.compute_lock_status(
            self.hand_num, hero_stack, opp_stack
        )
        if is_locked and mode == "LOCK_MODE":
            if "check" in legal and call_cost == 0:
                return ("check", 0)
            return ("fold", 0)

        tier = self.governor.get_tier(time_bank, self.hand_num)

        try:
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
                    self.hand_num,
                )
            else:
                act, amt = self.strategy.decide_postflop(
                    street,
                    self.hero_cards,
                    board,
                    self.is_button,
                    pot,
                    call_cost,
                    min_raise,
                    max_raise,
                    hero_stack,
                    opp_stack,
                    self.villain_weights,
                    compute_tier=tier,
                    hand_num=self.hand_num,
                )

            return ActionSanitizer.sanitize(
                act, amt, legal, min_raise, max_raise, pot
            )
        except Exception:
            if "check" in legal:
                return ("check", 0)
            if "call" in legal and call_cost <= 2:
                return ("call", 0)
            return ("fold", 0)

    def on_hand_end(self, hand_summary: Dict[str, Any]) -> None:
        try:
            showdown = hand_summary.get("showdown", False)
            if showdown:
                opp_cards_str = hand_summary.get("opp_hole_cards", [])
                bet_ratio = hand_summary.get("last_opp_bet_ratio", 0.0)
                if len(opp_cards_str) == 2:
                    opp_cards = [card_from_str(c) for c in opp_cards_str]
                    board_str = hand_summary.get("board", [])
                    board = [card_from_str(c) for c in board_str]
                    score = evaluate_7cards(opp_cards + board)
                    self.model.record_showdown(bet_ratio, score / (8 << 20))
        except Exception:
            pass
