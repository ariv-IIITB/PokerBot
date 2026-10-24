"""Kuhn poker, used to validate the MCCFR solver (game value for player 0 = -1/18).

Deck J, Q, K; each player antes 1 and gets one card; player 0 acts first.
Actions: 0 = pass (check / fold), 1 = bet (bet / call), bet size 1.
"""
from __future__ import annotations

import itertools

PASS, BET = 0, 1


class Kuhn:
    def root(self, rng):
        cards = rng.permutation(3)[:2]
        return (int(cards[0]), int(cards[1]), ())

    def chance_outcomes(self):
        for a, b in itertools.permutations(range(3), 2):
            yield (a, b, ()), 1.0 / 6

    def is_terminal(self, s) -> bool:
        h = s[2]
        return h in ((PASS, PASS), (BET, BET), (BET, PASS), (PASS, BET, PASS), (PASS, BET, BET))

    def utility(self, s, p: int) -> float:
        c0, c1, h = s
        winner0 = c0 > c1
        if h == (BET, PASS):
            u0 = 1.0                                        # player 1 folded
        elif h == (PASS, BET, PASS):
            u0 = -1.0                                       # player 0 folded
        elif h in ((BET, BET), (PASS, BET, BET)):
            u0 = 2.0 if winner0 else -2.0
        else:                                               # pass, pass
            u0 = 1.0 if winner0 else -1.0
        return u0 if p == 0 else -u0

    def to_act(self, s):
        return len(s[2]) % 2

    def chance(self, s, rng):
        return s

    def actions(self, s):
        return [PASS, BET]

    def play(self, s, a):
        return (s[0], s[1], s[2] + (a,))

    def infoset(self, s, p: int):
        return (s[p], s[2])
