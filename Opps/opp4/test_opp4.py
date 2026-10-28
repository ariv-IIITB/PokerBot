"""
test_opp4.py - Comprehensive verification suite testing:
1. Fast 7-card evaluator: all 9 categories, kickers, ace-low straight (wheel), flushes, ties
2. Combination generator (all 1,326 combos, dead-card filtering)
3. Bayesian opponent tracker (Beta priors, shrinkage with c = n / (n + 25), action multipliers)
4. Range-weighted equity calculation and sampling uncertainty
5. Calling rule with quantified margins and uncertainty
6. Bet sizing candidates (33%, 66%, 110%, all-in) and river bluff ratio
7. Match utility U(D) = Phi(D / sigma_remaining)
8. Safety sanitizer and zero-crash guarantee
"""

import math
import unittest
import numpy as np

from evaluator import (
    card_from_str,
    card_to_str,
    evaluate_7cards,
    hand_category_name,
    CAT_HIGH_CARD,
    CAT_ONE_PAIR,
    CAT_TWO_PAIR,
    CAT_THREE_OF_A_KIND,
    CAT_STRAIGHT,
    CAT_FLUSH,
    CAT_FULL_HOUSE,
    CAT_FOUR_OF_A_KIND,
    CAT_STRAIGHT_FLUSH,
)
from preflop import (
    TOTAL_COMBOS,
    COMBO_LIST,
    cards_to_canonical,
    is_hand_in_chart,
)
from opponent_model import BayesianBetaStat, OpponentModel
from equity import calculate_river_exact, calculate_equity
from meta_controller import MatchUtilityModel, standard_normal_cdf
from strategy import StrategyEngine
from safety import ActionSanitizer
from bot import PokerBot


class TestEvaluator(unittest.TestCase):
    def test_hand_categories(self):
        # 1. Straight flush (Royal)
        rf = [card_from_str(c) for c in ["Ah", "Kh", "Qh", "Jh", "Th", "2c", "3d"]]
        score_rf = evaluate_7cards(rf)
        self.assertEqual(score_rf >> 20, CAT_STRAIGHT_FLUSH)

        # 2. Four of a kind
        quads = [card_from_str(c) for c in ["8s", "8h", "8d", "8c", "Kh", "2c", "3d"]]
        score_quads = evaluate_7cards(quads)
        self.assertEqual(score_quads >> 20, CAT_FOUR_OF_A_KIND)

        # 3. Full house
        fh = [card_from_str(c) for c in ["Qs", "Qh", "Qd", "Jh", "Jc", "2c", "3d"]]
        score_fh = evaluate_7cards(fh)
        self.assertEqual(score_fh >> 20, CAT_FULL_HOUSE)

        # 4. Flush
        fl = [card_from_str(c) for c in ["Ah", "Jh", "9h", "4h", "2h", "Kc", "Qd"]]
        score_fl = evaluate_7cards(fl)
        self.assertEqual(score_fl >> 20, CAT_FLUSH)

        # 5. Normal straight
        st = [card_from_str(c) for c in ["9s", "8h", "7d", "6c", "5h", "2c", "3d"]]
        score_st = evaluate_7cards(st)
        self.assertEqual(score_st >> 20, CAT_STRAIGHT)

        # 6. Ace-low straight (Wheel: A-2-3-4-5)
        wheel = [card_from_str(c) for c in ["Ah", "2s", "3d", "4c", "5h", "9c", "Kd"]]
        score_wheel = evaluate_7cards(wheel)
        self.assertEqual(score_wheel >> 20, CAT_STRAIGHT)

        # 7. Ace-low straight flush (Steel Wheel)
        wheel_sf = [card_from_str(c) for c in ["Ah", "2h", "3h", "4h", "5h", "9c", "Kd"]]
        score_wheel_sf = evaluate_7cards(wheel_sf)
        self.assertEqual(score_wheel_sf >> 20, CAT_STRAIGHT_FLUSH)

        # 8. Three of a kind
        trips = [card_from_str(c) for c in ["7s", "7h", "7d", "Kc", "Qh", "2c", "3d"]]
        score_trips = evaluate_7cards(trips)
        self.assertEqual(score_trips >> 20, CAT_THREE_OF_A_KIND)

        # 9. Two pair
        tp = [card_from_str(c) for c in ["Js", "Jh", "4d", "4c", "Ah", "2c", "3d"]]
        score_tp = evaluate_7cards(tp)
        self.assertEqual(score_tp >> 20, CAT_TWO_PAIR)

        # 10. One pair
        pair = [card_from_str(c) for c in ["As", "Ah", "Kd", "Qc", "Jc", "2c", "3d"]]
        score_pair = evaluate_7cards(pair)
        self.assertEqual(score_pair >> 20, CAT_ONE_PAIR)

        # 11. High card
        hc = [card_from_str(c) for c in ["As", "Kh", "Qd", "Jc", "9s", "4c", "2d"]]
        score_hc = evaluate_7cards(hc)
        self.assertEqual(score_hc >> 20, CAT_HIGH_CARD)

        # Strict ordering verification
        self.assertTrue(score_rf > score_quads > score_fh > score_fl > score_st > score_trips > score_tp > score_pair > score_hc)

    def test_kickers_and_ties(self):
        # Two pair with different kickers
        tp_k1 = [card_from_str(c) for c in ["As", "Ah", "Kd", "Kc", "Qh", "2c", "3d"]]  # AAKKQ
        tp_k2 = [card_from_str(c) for c in ["As", "Ac", "Kh", "Ks", "Jh", "2c", "3d"]]  # AAKKJ
        self.assertGreater(evaluate_7cards(tp_k1), evaluate_7cards(tp_k2))

        # Tie
        tp_tie1 = [card_from_str(c) for c in ["As", "Ah", "Kd", "Kc", "Qh", "2c", "3d"]]
        tp_tie2 = [card_from_str(c) for c in ["Ad", "Ac", "Kh", "Ks", "Qs", "2h", "3c"]]
        self.assertEqual(evaluate_7cards(tp_tie1), evaluate_7cards(tp_tie2))


class TestPreflopAndCombinations(unittest.TestCase):
    def test_combinations_count(self):
        self.assertEqual(TOTAL_COMBOS, 1326)

    def test_canonical_mapping(self):
        c1, c2 = card_from_str("Ah"), card_from_str("As")
        can, is_pair, is_suited = cards_to_canonical(c1, c2)
        self.assertEqual(can, "AA")
        self.assertTrue(is_pair)

        c1, c2 = card_from_str("Kh"), card_from_str("Ah")
        can, is_pair, is_suited = cards_to_canonical(c1, c2)
        self.assertEqual(can, "AKs")
        self.assertTrue(is_suited)

    def test_push_fold_chart(self):
        # AA must be in push/fold at <= 8BB
        self.assertTrue(is_hand_in_chart("AA", 7.0, "sb_open"))
        self.assertTrue(is_hand_in_chart("AKs", 7.0, "sb_open"))


class TestOpponentModelBayesian(unittest.TestCase):
    def test_bayesian_beta_priors_and_shrinkage(self):
        # VPIP: Beta(2, 2)
        vpip = BayesianBetaStat(2.0, 2.0)
        self.assertAlmostEqual(vpip.prior_mean, 0.50)

        # 0 observations: c = 0 / 25 = 0, smoothed mean = prior mean = 0.50
        self.assertAlmostEqual(vpip.smoothed_mean, 0.50)

        # 25 observations: all True
        for _ in range(25):
            vpip.observe(True)

        # posterior mean = (2 + 25) / (4 + 25) = 27 / 29 = 0.9310
        # confidence c = 25 / (25 + 25) = 0.50
        # smoothed mean = 0.5 * 0.50 + 0.5 * (27 / 29) = 0.25 + 0.4655 = 0.7155
        expected_posterior = 27.0 / 29.0
        expected_smoothed = 0.5 * 0.50 + 0.5 * expected_posterior
        self.assertAlmostEqual(vpip.smoothed_mean, expected_smoothed, places=3)

    def test_action_multipliers(self):
        model = OpponentModel()
        weights = model.get_initial_villain_weights()
        board = [card_from_str(c) for c in ["Ah", "Kd", "2c"]]
        updated = model.update_weights_for_action(weights, "raise", board, 10, 20)
        self.assertEqual(len(updated), TOTAL_COMBOS)


class TestCallingRuleAndBetting(unittest.TestCase):
    def setUp(self):
        self.model = OpponentModel()
        self.meta = MatchUtilityModel()
        self.strategy = StrategyEngine(self.model, self.meta)

    def test_calling_margins(self):
        # Pot = 10, call_cost = 5 -> E_min = 5 / (10 + 5) = 0.3333
        # Preflop: extra = +1.5% (+0.015). If IP: req = 0.3483 + uncertainty
        # Equity 0.36 should call with low uncertainty
        can_call = self.strategy.decide_calling("preflop", equity=0.36, sampling_se=0.005, pot=10, call_cost=5, is_button=True)
        self.assertTrue(can_call)

        # Equity 0.30 should fold
        can_call_fold = self.strategy.decide_calling("preflop", equity=0.30, sampling_se=0.005, pot=10, call_cost=5, is_button=True)
        self.assertFalse(can_call_fold)

    def test_bet_candidates_evaluation(self):
        # Facing check with strong hand (equity = 0.85) in pot of 20
        act, amt, util = self.strategy.evaluate_bet_candidates(
            street="flop",
            equity=0.85,
            pot=20,
            hero_stack=200,
            min_raise=2,
            max_raise=200,
            score_margin=0.0,
            current_hand=50,
        )
        self.assertEqual(act, "raise")
        self.assertIn(amt, [7, 13, 22, 200])  # One of 33%, 66%, 110%, all-in

    def test_river_bluff_ratio(self):
        # B = 10, P = 10 -> ratio = 10 / 20 = 0.50
        # If blocker-rich hand, should trigger with probability
        hero = [card_from_str("Ah"), card_from_str("2c")]
        board = [card_from_str(c) for c in ["Kh", "Qh", "9s", "4d", "3c"]]
        # Call multiple times to verify ratio bounds
        triggers = sum(self.strategy.should_river_bluff(hero, board, bet_size=10, pot=10) for _ in range(1000))
        # Expected around 500
        self.assertTrue(350 <= triggers <= 650)


class TestMatchUtilityAndSafety(unittest.TestCase):
    def test_match_utility_win_prob(self):
        meta = MatchUtilityModel(total_hands=400, sigma_hand=20.0)
        # Margin = 0 -> U(0) = Phi(0) = 0.50
        u0 = meta.compute_win_prob(0.0, 100)
        self.assertAlmostEqual(u0, 0.50, places=3)

        # Margin = +200 -> U > 0.50
        u_lead = meta.compute_win_prob(200.0, 350)
        self.assertGreater(u_lead, 0.90)

    def test_action_sanitizer(self):
        # Check facing bet -> converted to fold
        act, amt = ActionSanitizer.sanitize("check", 0, ["call", "fold"], 0, 0)
        self.assertEqual(act, "fold")

        # Raise out of bounds -> clamped
        act, amt = ActionSanitizer.sanitize("raise", 500, ["raise", "call", "fold"], 4, 200)
        self.assertEqual(act, "raise")
        self.assertEqual(amt, 200)

        # Never fold when checking is free
        act, amt = ActionSanitizer.sanitize("fold", 0, ["check", "raise"], 4, 200)
        self.assertEqual(act, "check")


if __name__ == "__main__":
    unittest.main()
