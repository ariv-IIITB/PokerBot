"""Leduc Hold'em: a small poker game for measuring solver convergence exactly.

Deck: 6 cards, ranks J < Q < K with two suits each (card c has rank c // 2).
Each player antes 1 and gets one private card. Round 1: betting, player 0 first, raise
size 2. Then one public board card. Round 2: betting, player 0 first, raise size 4.
At most 2 raises per round (the first bet counts). Showdown: a card pairing the board
wins, otherwise the higher rank wins; equal ranks split.

History is a string over {"c" (check/call), "r" (bet/raise), "f" (fold)} with "/" between
rounds. Infosets use ranks only (suits never matter), which is lossless.
Implements the solver game interface of lab/cfr/mccfr.py plus `chance_outcomes()` /
`chance_children(s)` for exact evaluation (lab/cfr/exact.py).
"""
from __future__ import annotations

import itertools

RAISE_SIZES = (2, 4)
RAISE_CAP = 2
ANTE = 1


def _round_done(r: str) -> bool:
    return len(r) >= 2 and r[-1] == "c"


class Leduc:
    """State = (card0, card1, board (-1 = not dealt yet), history)."""

    def root(self, rng):
        a, b = rng.permutation(6)[:2]
        return (int(a), int(b), -1, "")

    def chance_outcomes(self):
        for a, b in itertools.permutations(range(6), 2):
            yield (a, b, -1, ""), 1.0 / 30

    def chance_children(self, s):
        c0, c1, _, h = s
        rest = [c for c in range(6) if c not in (c0, c1)]
        return [((c0, c1, c, h + "/"), 1.0 / len(rest)) for c in rest]

    # ---- structure
    @staticmethod
    def _rounds(h: str) -> list[str]:
        return h.split("/")

    def is_terminal(self, s) -> bool:
        h = s[3]
        if h.endswith("f"):
            return True
        rounds = self._rounds(h)
        return len(rounds) == 2 and _round_done(rounds[1])

    def to_act(self, s):
        c0, c1, board, h = s
        rounds = self._rounds(h)
        if len(rounds) == 1 and _round_done(rounds[0]):
            return None                                     # deal the board
        return len(rounds[-1]) % 2

    def chance(self, s, rng):
        kids = self.chance_children(s)
        return kids[int(rng.integers(len(kids)))][0]

    def actions(self, s):
        r = self._rounds(s[3])[-1]
        raises = r.count("r")
        facing = r.endswith("r")
        acts = (["f", "c"] if facing else ["c"])
        if raises < RAISE_CAP:
            acts.append("r")
        return acts

    def play(self, s, a):
        return (s[0], s[1], s[2], s[3] + a)

    def infoset(self, s, p: int):
        c0, c1, board, h = s
        mine = (c0, c1)[p] // 2
        return (mine, board // 2 if board >= 0 else -1, h)

    # ---- payoffs
    @staticmethod
    def contributions(h: str) -> tuple[list[int], int]:
        """(chips each player put in, index of the player who folded or -1)."""
        total = [ANTE, ANTE]
        folded = -1
        for i, r in enumerate(h.split("/")):
            bet = [0, 0]
            for j, a in enumerate(r):
                p = j % 2
                if a == "r":
                    bet[p] = bet[1 - p] + RAISE_SIZES[i]
                elif a == "c":
                    bet[p] = bet[1 - p]
                else:
                    folded = p
            total = [total[0] + bet[0], total[1] + bet[1]]
        return total, folded

    def utility(self, s, p: int) -> float:
        c0, c1, board, h = s
        total, folded = self.contributions(h)
        if folded >= 0:
            u0 = total[1] if folded == 1 else -total[0]
        else:
            r0, r1, rb = c0 // 2, c1 // 2, board // 2
            s0 = (2, r0) if r0 == rb else (1, r0)
            s1 = (2, r1) if r1 == rb else (1, r1)
            u0 = total[1] if s0 > s1 else (-total[0] if s1 > s0 else 0)
        return float(u0 if p == 0 else -u0)
