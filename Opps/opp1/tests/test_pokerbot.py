"""
Comprehensive unit tests for TitanBot and the Pokerbot framework.
"""

import unittest
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction
from skeleton.states import (
    GameState,
    TerminalState,
    RoundState,
    STARTING_STACK,
    BIG_BLIND,
    SMALL_BLIND,
)
from skeleton.evaluate import (
    evaluate_hand,
    hand_category,
    canonical_hand,
    get_preflop_equity,
    estimate_equity,
    get_draws,
    PREFLOP_EQUITY,
)
from player import TitanBot
from baselines import AlwaysCallBot, AlwaysFoldBot, TightBot, RandomBot
from engine import MatchEngine, DuplicateDeal


class TestEvaluator(unittest.TestCase):
    """Tests the Cactus Kev 5-to-7 card evaluator."""

    def test_hand_rankings(self):
        rf = ["Ah", "Kh", "Qh", "Jh", "Th"]
        quads = ["Kh", "Ks", "Kd", "Kc", "2c"]
        fh = ["Qh", "Qs", "Qd", "Jh", "Js"]
        flush = ["Ah", "Jh", "9h", "4h", "2h"]
        straight = ["9h", "8s", "7d", "6c", "5h"]
        trips = ["8h", "8s", "8d", "Kc", "2h"]
        two_pair = ["Jh", "Js", "4d", "4c", "Ah"]
        pair = ["Ah", "As", "Kd", "Qc", "2h"]
        high_card = ["Ah", "Kd", "Qc", "Jc", "9h"]

        score_rf = evaluate_hand(rf)
        score_quads = evaluate_hand(quads)
        score_fh = evaluate_hand(fh)
        score_flush = evaluate_hand(flush)
        score_straight = evaluate_hand(straight)
        score_trips = evaluate_hand(trips)
        score_tp = evaluate_hand(two_pair)
        score_pair = evaluate_hand(pair)
        score_hc = evaluate_hand(high_card)

        # Cactus Kev: lower score is strictly better
        self.assertTrue(score_rf < score_quads < score_fh < score_flush <
                        score_straight < score_trips < score_tp < score_pair < score_hc)

        self.assertEqual(hand_category(score_rf), "Straight Flush")
        self.assertEqual(hand_category(score_quads), "Four of a Kind")
        self.assertEqual(hand_category(score_fh), "Full House")
        self.assertEqual(hand_category(score_flush), "Flush")
        self.assertEqual(hand_category(score_straight), "Straight")
        self.assertEqual(hand_category(score_trips), "Three of a Kind")
        self.assertEqual(hand_category(score_tp), "Two Pair")
        self.assertEqual(hand_category(score_pair), "One Pair")
        self.assertEqual(hand_category(score_hc), "High Card")

    def test_7_card_eval(self):
        # 7 cards with hidden full house
        cards = ["Ah", "As", "Ad", "Kh", "Ks", "2c", "3d"]
        score = evaluate_hand(cards)
        self.assertEqual(hand_category(score), "Full House")

    def test_canonical_hand(self):
        self.assertEqual(canonical_hand("Ah", "As"), "AA")
        self.assertEqual(canonical_hand("Kh", "Ah"), "AKs")
        self.assertEqual(canonical_hand("2s", "7c"), "72o")
        self.assertEqual(len(PREFLOP_EQUITY), 169)

    def test_preflop_equity_lookups(self):
        aa_eq = get_preflop_equity("Ah", "As")
        kk_eq = get_preflop_equity("Kh", "Ks")
        t72o_eq = get_preflop_equity("7h", "2c")
        self.assertTrue(aa_eq > kk_eq > 0.80)
        self.assertTrue(t72o_eq < 0.36)

    def test_draws_detection(self):
        # 4 to a flush
        draws = get_draws(["Ah", "Kh"], ["Qh", "2h", "7c"])
        self.assertTrue(draws["flush_draw"])

        # Open-ended straight draw
        draws_str = get_draws(["8h", "9s"], ["7c", "6d", "2c"])
        self.assertTrue(draws_str["oesd"])

    def test_equity_monte_carlo(self):
        # Flop: set of Aces on A-7-2 rainbow
        eq = estimate_equity(["Ah", "As"], ["Ac", "7d", "2s"], n_samples=200, time_budget=0.03)
        self.assertGreater(eq, 0.90)


class TestTitanBotSafety(unittest.TestCase):
    """Verifies that TitanBot never crashes and only produces legal actions."""

    def setUp(self):
        self.bot = TitanBot()

    def test_preflop_actions_legal(self):
        # Round 1: Button action
        rs = RoundState(
            button=0,
            street=0,
            pips=[1, 2],
            stacks=[199, 198],
            hands=[["Ah", "Kd"], None],
            deck=[],
            previous_state=None,
        )
        gs = GameState(0, 60.0, 1)
        action = self.bot.get_action(gs, rs, active=0)
        legal = rs.legal_actions()
        self.assertIn(type(action), legal)

    def test_postflop_facing_check(self):
        rs = RoundState(
            button=0,
            street=3,
            pips=[0, 0],
            stacks=[196, 196],
            hands=[["Kh", "Qh"], None],
            deck=["Jh", "Th", "2c"],
            previous_state=None,
        )
        gs = GameState(0, 50.0, 1)
        action = self.bot.get_action(gs, rs, active=0)
        legal = rs.legal_actions()
        self.assertIn(type(action), legal)

    def test_postflop_facing_bet(self):
        rs = RoundState(
            button=0,
            street=3,
            pips=[0, 8],
            stacks=[196, 188],
            hands=[["7c", "2s"], None],
            deck=["Ah", "Kd", "Qc"],
            previous_state=None,
        )
        gs = GameState(0, 50.0, 1)
        action = self.bot.get_action(gs, rs, active=0)
        legal = rs.legal_actions()
        self.assertIn(type(action), legal)


class TestDuplicateMatchEngine(unittest.TestCase):
    """Verifies duplicate match engine and fairness."""

    def test_duplicate_deal_symmetry(self):
        deal = DuplicateDeal.generate_random()
        self.assertEqual(len(deal.hand_a), 2)
        self.assertEqual(len(deal.hand_b), 2)
        self.assertEqual(len(deal.board), 5)

        # Check all 9 cards are unique
        all_9 = deal.hand_a + deal.hand_b + deal.board
        self.assertEqual(len(set(all_9)), 9)

    def test_match_execution(self):
        engine = MatchEngine(TitanBot(), AlwaysCallBot(), total_rounds=20, time_bank=10.0)
        res = engine.play_duplicate_match()
        self.assertEqual(res["hands"], 20)
        self.assertEqual(res["winner"], "TitanBot")
        self.assertEqual(res["timeouts"]["TitanBot"], 0)


if __name__ == "__main__":
    unittest.main()
