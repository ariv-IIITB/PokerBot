"""Drives player.Player through random valid MIT-style RoundStates; every action must be legal."""
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "fake_skeleton"))

from skeleton.actions import CallAction, CheckAction, FoldAction, RaiseAction  # noqa: E402
from skeleton.states import GameState, RoundState, TerminalState  # noqa: E402
from player import Player  # noqa: E402
from pb.cards import to_str  # noqa: E402


def random_state(rng, active):
    deck = list(range(52))
    rng.shuffle(deck)
    cards = [to_str(c) for c in deck]
    street = rng.choice([0, 3, 4, 5])
    hands = [cards[0:2], cards[2:4]]
    board = cards[4:9]
    contrib = rng.choice([2, 4, 10, 40, 100, 200, 400])
    stacks = [400 - contrib, 400 - contrib]
    pips = [0, 0]
    if street == 0:
        pips = [1, 2] if active == 0 else [2, 1]
        pips = [1, 2]
        stacks = [399, 398]
        if rng.random() < 0.5:
            pips = [rng.randint(2, 100)] * 2
            pips[1 - active] += rng.randint(0, 50)
            stacks = [400 - pips[0], 400 - pips[1]]
    else:
        base = rng.randint(2, 200)
        stacks = [400 - base, 400 - base]
        a, b = rng.choice([(0, 0), (0, rng.randint(2, 60)), (rng.randint(2, 60), 0)])
        pips = [a, b] if active == 0 else [b, a]
        stacks = [stacks[0] - pips[0], stacks[1] - pips[1]]
        if rng.random() < 0.15:
            stacks[1 - active] = 0
    stacks = [max(0, s) for s in stacks]
    # in the engine, the player to act always has pips <= opponent's unless equal
    return RoundState(active, street, pips, stacks, hands, board, None)


class TestAdapter(unittest.TestCase):
    def test_random_states_always_legal(self):
        rng = random.Random(7)
        p = Player()
        for rnd in range(1, 301):
            active = rnd % 2
            rs = random_state(rng, active)
            gs = GameState(rng.randint(-300, 300), 50.0, rnd)
            p.handle_new_round(gs, rs, active)
            # make the state valid: acting player must not be ahead on pips
            act = p.get_action(gs, rs, active)
            legal = rs.legal_actions()
            self.assertIn(type(act), legal, (rs, act))
            if isinstance(act, RaiseAction):
                lo, hi = rs.raise_bounds()
                self.assertTrue(lo <= act.amount <= hi, (lo, hi, act))
            term = TerminalState([5, -5], rs)
            p.handle_round_over(gs, term, active)

    def test_survives_garbage(self):
        p = Player()
        gs = GameState(0, 50.0, 1)
        rs = RoundState(0, 0, [1, 2], [399, 398], [["As", "Ah"], []], [], None)
        a = p.get_action(gs, rs, 0)
        self.assertIn(type(a), rs.legal_actions())
        # broken state object -> must still return something legal-looking, never raise
        class Broken:
            def legal_actions(self): return {FoldAction, CallAction}
        out = p.get_action(gs, Broken(), 0)
        self.assertIsInstance(out, (FoldAction, CallAction, CheckAction))


if __name__ == "__main__":
    unittest.main()
