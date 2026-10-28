import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pb.cards import parse_many  # noqa: E402
from pb.types import CALL, CHECK, FOLD, RAISE  # noqa: E402
from sim.baselines import BaseBot, CallBot, RandomBot, ShoveBot  # noqa: E402
from sim.engine import Engine, Seat  # noqa: E402


class Scripted(BaseBot):
    def __init__(self, script):
        super().__init__()
        self.script = list(script)
        self.seen = []

    def act(self, obs):
        self.seen.append(obs)
        return self.script.pop(0) if self.script else (CHECK,) if obs.can_check else (FOLD,)


def run(bot0, bot1, hole0="As Ah", hole1="Kd Kc", board="2c 7d 9h Jc 3s"):
    e = Engine()
    s = [Seat(bot0, 1e9), Seat(bot1, 1e9)]
    d = e.play_hand(s, 0, [parse_many(hole0.split()), parse_many(hole1.split())],
                    parse_many(board.split()), 0, 100, [0, 0])
    return d, s


class TestEngine(unittest.TestCase):
    def test_sb_fold_loses_one(self):
        d, _ = run(Scripted([(FOLD,)]), Scripted([]))
        self.assertEqual(d, (-1, 1))

    def test_bb_fold_to_open_loses_two(self):
        d, _ = run(Scripted([(RAISE, 6)]), Scripted([(FOLD,)]))
        self.assertEqual(d, (2, -2))

    def test_limp_check_to_showdown(self):
        d, _ = run(Scripted([(CALL,)]), Scripted([]))   # AA beats KK, 2 chips each
        self.assertEqual(d, (2, -2))

    def test_min_raise_bounds(self):
        b1 = Scripted([(RAISE, 6)])
        b0 = Scripted([(RAISE, 6)])
        run(b0, b1)
        o = b1.seen[0]                      # BB facing raise to 6
        self.assertEqual((o.min_raise, o.max_raise), (10, 400))   # call 4 + raise by 4 => 10

    def test_all_in_runout_and_split(self):
        d, _ = run(Scripted([(RAISE, 400)]), Scripted([(CALL,)]), "As Kd", "Ah Ks", "2c 7d 9h Jc 3s")
        self.assertEqual(d, (0, 0))

    def test_all_in_win(self):
        d, _ = run(Scripted([(RAISE, 400)]), Scripted([(CALL,)]))
        self.assertEqual(d, (400, -400))

    def test_illegal_action_is_corrected(self):
        d, s = run(Scripted([(RAISE, 5000)]), Scripted([]))   # out-of-bounds raise -> becomes fold/check
        self.assertEqual(s[0].illegal, 1)

    def test_conservation_and_fuzz(self):
        rng = np.random.default_rng(1)
        e = Engine()
        for h in range(600):
            deck = rng.permutation(52)
            bots = [RandomBot(h), RandomBot(h + 1)] if h % 3 else [ShoveBot(), RandomBot(h)]
            s = [Seat(bots[0], 1e9), Seat(bots[1], 1e9)]
            d = e.play_hand(s, 0, [deck[0:2], deck[2:4]], deck[4:9], h, 100, [0, 0])
            self.assertEqual(d[0] + d[1], 0)
            self.assertTrue(-400 <= d[0] <= 400)
            self.assertEqual(s[0].illegal + s[1].illegal, 0)


if __name__ == "__main__":
    unittest.main()
