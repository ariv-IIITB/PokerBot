import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pb.brain import Brain  # noqa: E402
from pb.types import CALL, CHECK, FOLD, RAISE, Obs  # noqa: E402
from sim.match import play_match  # noqa: E402


def legal(obs, a):
    if a[0] == RAISE:
        return obs.can_raise and obs.min_raise <= a[1] <= obs.max_raise
    if a[0] == CHECK:
        return obs.can_check
    if a[0] == CALL:
        return obs.to_call > 0
    if a[0] == FOLD:
        return not obs.can_check
    return False


class TestBrain(unittest.TestCase):
    def test_full_matches_no_faults(self):
        for opp in ("random", "maniac", "shove", "lag", "tag"):
            r = play_match(("brain:fast", opp, 120, 99, 60.0, "bot"))
            self.assertEqual(r["crash_a"], 0, opp)
            self.assertEqual(r["illegal_a"], 0, opp)
            self.assertIsNone(r["forfeit"], opp)

    def test_tiny_time_bank_never_times_out(self):
        # 2 s per 400 hands: the Brain must degrade (lean/panic) rather than time out
        r = play_match(("brain", "lag", 200, 5, 2.0, "bot"))
        self.assertIsNone(r["forfeit"])
        self.assertLess(r["time_a"], 2.0 * 200 / 400)

    def test_normal_bank_leaves_large_margin(self):
        r = play_match(("brain", "tag", 400, 8, 60.0, "bot"))
        self.assertLess(r["time_a"], 30.0)
        self.assertLess(r["max_a"], 1.0)

    def test_garbage_obs_returns_something_legal(self):
        b = Brain(max_samples=100)
        rng = random.Random(3)
        for i in range(300):
            can_check = rng.random() < 0.5
            tc = 0 if can_check else rng.randint(1, 300)
            can_raise = rng.random() < 0.8
            o = Obs(hand_no=i, hole=tuple(rng.sample(range(52), rng.choice([2, 2, 2, 1, 3]))),
                    board=tuple(rng.sample(range(52), rng.choice([0, 3, 4, 5]))),
                    street=rng.randint(0, 3), button=rng.random() < 0.5, pot=rng.randint(3, 800),
                    hero_pip=rng.randint(0, 50), opp_pip=rng.randint(0, 100), hero_stack=rng.randint(0, 400),
                    opp_stack=rng.randint(0, 400), to_call=tc, min_raise=10 if can_raise else 0,
                    max_raise=rng.randint(10, 400) if can_raise else 0, can_check=can_check,
                    can_raise=can_raise, time_left=rng.choice([None, 50.0, 0.5, 0.0, -3.0]),
                    hands_left=rng.randint(1, 400), bankroll=rng.randint(-2000, 2000))
            a = b.act(o)
            if len(o.hole) == 2:           # for malformed hole sizes we only require "no exception"
                self.assertTrue(legal(o, a) or (a[0] == FOLD and o.can_fold), (o, a))


if __name__ == "__main__":
    unittest.main()
