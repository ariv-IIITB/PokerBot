"""Betting abstraction shared by the CFR trainer (lab/cfr/) and any brain that plays a trained
strategy. It lives in bot/ so the runtime keys a decision exactly as the trainer did.

Buckets: our equity vs a random hand (bot.equity, the one showdown rule), estimated with an
rng seeded from the cards, so the same cards always get the same bucket; cut into `n_buckets`.
History: abstract action labels, "/" after the last action of each street (extend_history).
Infoset key: "street|bucket|history".
Actions: fold, check/call, raise to ~0.5 pot, ~1 pot, all-in ("F", "C", "H", "P", "A"),
filtered to what is legal and de-duplicated by amount.
Opponent bets that are not exactly an abstract size are mapped to the neighbouring sizes
with the pseudo-harmonic rule (Ganzfried & Sandholm): for x between sizes A < x < B (as pot
fractions), P(map to A) = (B - x)(1 + A) / ((B - A)(1 + x)).
"""
from __future__ import annotations

import zlib
from typing import Optional, Tuple

import numpy as np

from bot.actions import Action, LegalActions, pot_fraction_raise
from bot.equity import equity_vectorized

FRACTIONS = {"H": 0.5, "P": 1.0}
ORDER = ("F", "C", "H", "P", "A")


def abstract_actions(legal: LegalActions, pot: int, to_call: int, mybet: int,
                     fractions: Optional[dict] = None) -> list[tuple[str, Action]]:
    """(label, concrete action) pairs for the abstract actions legal here.
    `fractions`: raise label -> pot fraction (default FRACTIONS); all-in is always "A"."""
    out: list[tuple[str, Action]] = []
    if legal.fold:
        out.append(("F", Action.fold()))
    out.append(("C", Action.call() if legal.call else Action.check()))
    if legal.can_raise:
        seen = set()
        for label, frac in (fractions or FRACTIONS).items():
            a = pot_fraction_raise(frac, pot, to_call, mybet, legal)
            if a is not None and a.amount not in seen:
                seen.add(a.amount)
                out.append((label, a))
        allin = Action.raise_to(legal.raise_max)  # type: ignore[arg-type]
        if allin.amount not in seen:
            out.append(("A", allin))
    return out


def raise_label(amount: int, pot_before: int, call_before: int, bet_before: int,
                rng: Optional[np.random.Generator] = None, all_in: bool = False,
                fractions: Optional[dict] = None) -> str:
    """Abstract label for an observed raise to `amount` (pseudo-harmonic between sizes)."""
    if all_in:
        return "A"
    denom = max(1, pot_before + call_before)
    x = (amount - bet_before - call_before) / denom          # the raise as a pot fraction
    sizes = sorted((fractions or FRACTIONS).items(), key=lambda kv: kv[1])
    if x <= sizes[0][1]:
        return sizes[0][0]
    if x >= sizes[-1][1]:
        return sizes[-1][0]
    for (la, a), (lb, b) in zip(sizes, sizes[1:]):
        if a <= x <= b:
            p_a = (b - x) * (1 + a) / ((b - a) * (1 + x))
            u = rng.random() if rng is not None else 0.5
            return la if u < p_a else lb
    return sizes[-1][0]


class Bucketer:
    """Hand-strength buckets, cached. Same answer for the same cards, always."""

    def __init__(self, rules, n_buckets: int = 8, ref: int = 64) -> None:
        self.rules, self.n, self.ref = rules, n_buckets, ref
        self.cache: dict = {}

    def bucket(self, hole, board) -> int:
        key = (tuple(sorted(hole)), tuple(sorted(board)))
        b = self.cache.get(key)
        if b is None:
            b = self.cache[key] = self._compute(list(hole), list(board))
        return b

    def _compute(self, hole, board) -> int:
        seed = zlib.crc32(bytes(str((sorted(hole), sorted(board))), "ascii"))
        try:
            eq = equity_vectorized(hole, board, self.rules, max_samples=self.ref,
                                   rng=np.random.default_rng(seed), first_chunk=self.ref,
                                   opp_cards=len(hole)).equity      # same count as ours (post-discard)
        except (ValueError, IndexError):
            eq = 0.5
        return min(self.n - 1, int(eq * self.n))


def infoset_key(player_street: int, bucket: int, history: str) -> str:
    return f"{player_street}|{bucket}|{history}"


def extend_history(history: str, label: str, street_before: int, street_after: int) -> str:
    """The abstract history after one more action: its label, then "/" if it closed the street."""
    return history + label + ("/" if street_after != street_before else "")


def observed_label(action: Action, legal_before: LegalActions, pot: int, to_call: int,
                   bet: int, all_in: bool, rng: Optional[np.random.Generator] = None,
                   fractions: Optional[dict] = None) -> Tuple[str, bool]:
    """(label, translated?) for an action seen at run time. A raise the abstraction could have
    made (same amount) gets exactly its training label; other sizes are translated
    pseudo-harmonically (translated = True)."""
    if action.kind == "F":
        return "F", False
    if action.kind in ("C", "K"):
        return "C", False
    exact = [name for name, x in abstract_actions(legal_before, pot, to_call, bet, fractions)
             if x.kind == action.kind and x.amount == action.amount]
    if exact:
        return exact[0], False
    return raise_label(action.amount, pot, to_call, bet, rng, all_in, fractions), True


# --------------------------------------------------------------------------- v2 buckets
# docs/cfr/ABSTRACTION_V1.md section 5. Every feature is an exact ratio of integer counts, so the
# Numba twin (lab/cfr/fast/buckets.py) computes bit-identical floats and bucket ids.

MASK64 = (1 << 64) - 1
GOLDEN = 0x9E3779B97F4A7C15
MIX1 = 0xBF58476D1CE4E5B9
MIX2 = 0x94D049BB133111EB
SEED_BASE = 0x5EED0000
SEPARATOR = 255
FLOP_RUNOUTS, FLOP_OPP, TURN_OPP = 50, 40, 24


def _mix_int(z: int) -> int:
    z = ((z ^ (z >> 30)) * MIX1) & MASK64
    z = ((z ^ (z >> 27)) * MIX2) & MASK64
    return z ^ (z >> 31)


def card_seed(street: int, hole, board, dead=()) -> int:
    """The sampler seed for these cards (order-independent)."""
    s = SEED_BASE + street
    for c in [*sorted(hole), SEPARATOR, *sorted(board), SEPARATOR, *sorted(dead)]:
        s = _mix_int(((s ^ int(c)) + GOLDEN) & MASK64)
    return s


def splitmix_stream(seed: int, n: int) -> np.ndarray:
    """The first n SplitMix64 outputs from state `seed` (uint64)."""
    with np.errstate(over="ignore"):
        z = np.uint64(seed) + np.uint64(GOLDEN) * np.arange(1, n + 1, dtype=np.uint64)
        z = (z ^ (z >> np.uint64(30))) * np.uint64(MIX1)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(MIX2)
        return z ^ (z >> np.uint64(31))


def _pair(d1: np.ndarray, d2: np.ndarray, m: int) -> tuple[np.ndarray, np.ndarray]:
    """Two distinct indices in [0, m) from two draws."""
    i = (d1 % np.uint64(m)).astype(np.int64)
    j = (d2 % np.uint64(m - 1)).astype(np.int64)
    return i, j + (j >= i)


def _skip(k: np.ndarray, *removed: np.ndarray) -> np.ndarray:
    """Index into a list with the `removed` positions (ascending) taken out -> original index."""
    for r in removed:
        k = k + (k >= r)
    return k


def _counts(ev, mine: np.ndarray, opp: np.ndarray, boards: np.ndarray) -> np.ndarray:
    """2 x wins + ties of `mine` against `opp`, per row (int64)."""
    a = ev.evaluate_batch(mine, boards)
    b = ev.evaluate_batch(opp, boards)
    return 2 * (a > b).astype(np.int64) + (a == b)


def flop_features(ev, hole3, board3) -> tuple[int, float, float]:
    """(best keep index, E[HS], E[HS^2]) on the flop, before the discard (section 5.2).
    Keeps are the 2-card subsets of sorted(hole3) in combinations order: (0,1), (0,2), (1,2)."""
    hole = sorted(int(c) for c in hole3)
    board = [int(c) for c in board3]
    unseen = np.array(sorted(set(range(52)) - set(hole) - set(board)), dtype=np.int64)
    m, R, O = len(unseen), FLOP_RUNOUTS, FLOP_OPP
    d = splitmix_stream(card_seed(1, hole, board), R * (2 + 2 * O)).reshape(R, 2 + 2 * O)
    i, j = _pair(d[:, 0], d[:, 1], m)
    lo, hi = np.minimum(i, j), np.maximum(i, j)
    a, b = _pair(d[:, 2::2], d[:, 3::2], m - 2)
    oa = unseen[_skip(a, lo[:, None], hi[:, None])]
    ob = unseen[_skip(b, lo[:, None], hi[:, None])]
    boards = np.concatenate([np.broadcast_to(board, (R, 3)), unseen[i][:, None], unseen[j][:, None]], axis=1)
    rows = np.repeat(boards, O, axis=0)
    opp = np.stack([oa.ravel(), ob.ravel()], axis=1)
    keeps = [(0, 1), (0, 2), (1, 2)]
    best = (-1, 0, 0)
    for k, (x, y) in enumerate(keeps):
        mine = np.broadcast_to(np.array([hole[x], hole[y]], dtype=np.int64), (R * O, 2))
        cnt = _counts(ev, mine, opp, rows).reshape(R, O).sum(axis=1)
        s1, s2 = int(cnt.sum()), int((cnt * cnt).sum())
        if s1 > best[1] or best[0] < 0:
            best = (k, s1, s2)
    k, s1, s2 = best
    return k, s1 / (2 * O * R), s2 / ((2 * O) ** 2 * R)


def turn_features(ev, hole2, board4, dead) -> tuple[float, float]:
    """(E[HS], E[HS^2]) on the turn: every river, TURN_OPP sampled opponent hands each (5.3)."""
    hole = sorted(int(c) for c in hole2)
    board = [int(c) for c in board4]
    unseen = np.array(sorted(set(range(52)) - set(hole) - set(board) - {int(c) for c in dead}),
                      dtype=np.int64)
    m, O = len(unseen), TURN_OPP
    d = splitmix_stream(card_seed(2, hole, board, dead), m * 2 * O).reshape(m, 2 * O)
    a, b = _pair(d[:, 0::2], d[:, 1::2], m - 1)
    r = np.arange(m)[:, None]
    opp = np.stack([unseen[_skip(a, r)].ravel(), unseen[_skip(b, r)].ravel()], axis=1)
    boards = np.repeat(np.concatenate([np.broadcast_to(board, (m, 4)), unseen[:, None]], axis=1), O, axis=0)
    mine = np.broadcast_to(np.array(hole, dtype=np.int64), (m * O, 2))
    cnt = _counts(ev, mine, opp, boards).reshape(m, O).sum(axis=1)
    return int(cnt.sum()) / (2 * O * m), int((cnt * cnt).sum()) / ((2 * O) ** 2 * m)


def river_features(ev, hole2, board5, dead) -> tuple[float, int]:
    """(exact HS against every opponent 2-card hand, flush-blocker bit) on the river (5.4)."""
    hole = sorted(int(c) for c in hole2)
    board = [int(c) for c in board5]
    unseen = sorted(set(range(52)) - set(hole) - set(board) - {int(c) for c in dead})
    opp = np.array([(x, y) for n, x in enumerate(unseen) for y in unseen[n + 1:]], dtype=np.int64)
    n = len(opp)
    cnt = _counts(ev, np.broadcast_to(np.array(hole, dtype=np.int64), (n, 2)), opp,
                  np.broadcast_to(np.array(board, dtype=np.int64), (n, 5)))
    suits = [c & 3 for c in board]
    blocker = int(any(suits.count(c & 3) >= 3 for c in hole))
    return int(cnt.sum()) / (2 * n), blocker


def grid_bucket(x: float, y: float, x_cuts, y_cuts) -> int:
    """10 x 10 cell: x bin from x_cuts (9), then y bin from y_cuts[xbin] (9 each)."""
    xb = int(np.searchsorted(x_cuts, x, side="right"))
    yb = int(np.searchsorted(y_cuts[xb], y, side="right"))
    return (len(y_cuts[xb]) + 1) * xb + yb


def river_bucket(hs: float, blocker: int, cuts) -> int:
    return 2 * int(np.searchsorted(cuts, hs, side="right")) + int(blocker)
