import itertools
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pb.cards import parse_many  # noqa: E402
from pb.evaluator import category, evaluate, evaluate_one  # noqa: E402


def ref5(cards):
    """Independent, slow 5-card evaluator returning a comparable tuple."""
    ranks = sorted((c % 13 for c in cards), reverse=True)
    suits = [c // 13 for c in cards]
    flush = len(set(suits)) == 1
    uniq = sorted(set(ranks), reverse=True)
    straight_high = None
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_high = uniq[0]
        elif uniq == [12, 3, 2, 1, 0]:
            straight_high = 3
    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    shape = [g[1] for g in groups]
    order = [g[0] for g in groups]
    if flush and straight_high is not None:
        return (8, straight_high)
    if shape == [4, 1]:
        return (7, *order)
    if shape == [3, 2]:
        return (6, *order)
    if flush:
        return (5, *ranks)
    if straight_high is not None:
        return (4, straight_high)
    if shape == [3, 1, 1]:
        return (3, *order)
    if shape == [2, 2, 1]:
        return (2, *order)
    if shape == [2, 1, 1, 1]:
        return (1, *order)
    return (0, *ranks)


def ref_best(cards):
    return max(ref5(c) for c in itertools.combinations(cards, 5))


class TestEvaluator(unittest.TestCase):
    def test_categories(self):
        cases = {
            8: "9h 8h 7h 6h 5h 2c Kd",
            7: "Ks Kh Kd Kc 3c 4d 9s",
            6: "Ks Kh Kd 3c 3d 4d 9s",
            5: "As 9s 7s 5s 2s Kd Qh",
            4: "9s 8d 7h 6c 5s 2d Kh",
            3: "Qs Qh Qd 3c 8d 4d 9s",
            2: "Qs Qh 8d 8c 3d 4d 9s",
            1: "Qs Qh 7d 8c 3d 4d 9s",
            0: "As Jh 7d 8c 3d 4d 9s",
        }
        for cat, s in cases.items():
            self.assertEqual(int(category(evaluate_one(parse_many(s.split())))), cat, s)

    def test_wheel_and_edge_cases(self):
        wheel = evaluate_one(parse_many("As 2d 3h 4c 5s 9d Kh".split()))
        six_high = evaluate_one(parse_many("2s 3d 4h 5c 6s 9d Kh".split()))
        self.assertLess(wheel, six_high)
        self.assertEqual(int(category(wheel)), 4)
        # three pairs: best two pairs + best kicker
        a = evaluate_one(parse_many("7s 7d 5h 5c 3s 3d Ah".split()))
        b = evaluate_one(parse_many("7s 7d 5h 5c Ks 2d 4h".split()))
        self.assertGreater(a, b)  # kicker A beats K
        # two trips make a full house
        fh = evaluate_one(parse_many("7s 7d 7h 5c 5s 5d Ah".split()))
        self.assertEqual(int(category(fh)), 6)
        # quads with trips on the side
        q = evaluate_one(parse_many("7s 7d 7h 7c 5s 5d 5h".split()))
        self.assertEqual(int(category(q)), 7)
        # straight flush beats quads
        sf = evaluate_one(parse_many("9h 8h 7h 6h 5h 9s 9d".split()))
        self.assertEqual(int(category(sf)), 8)
        # flush uses the flush suit only, even when a straight exists in other suits
        fl = evaluate_one(parse_many("2h 5h 9h Jh Kh 6d 7s".split()))
        self.assertEqual(int(category(fl)), 5)

    def test_matches_reference_7card(self):
        rng = np.random.default_rng(123)
        n = 1500
        for k in (7, 6, 5):
            decks = np.argsort(rng.random((n * 2, 52)), axis=1)[:, :k]
            sc = evaluate(decks)
            for i in range(n):
                a, b = decks[2 * i], decks[2 * i + 1]
                ra, rb = ref_best(list(a)), ref_best(list(b))
                exp = int(ra > rb) - int(ra < rb)
                got = int(sc[2 * i] > sc[2 * i + 1]) - int(sc[2 * i] < sc[2 * i + 1])
                self.assertEqual(exp, got, (list(a), list(b)))

    def test_category_frequencies(self):
        rng = np.random.default_rng(5)
        decks = np.argsort(rng.random((40000, 52)), axis=1)[:, :7]
        cats = np.bincount(category(evaluate(decks)).astype(int), minlength=9) / 40000
        # known 7-card frequencies: high .174, pair .438, two pair .235, trips .048,
        # straight .046, flush .030, FH .026, quads .0017, SF .0003
        for got, exp, tol in [(cats[0], .174, .01), (cats[1], .438, .012), (cats[2], .235, .01),
                              (cats[3], .048, .005), (cats[4], .046, .005), (cats[5], .030, .004),
                              (cats[6], .026, .004)]:
            self.assertAlmostEqual(got, exp, delta=tol)


if __name__ == "__main__":
    unittest.main()
