"""Game abstraction shared by the MCCFR trainer (lab/cfr) and the CFR brain.

Buckets: hand strength = percentile of our hand vs random hands on the current board
(deterministic: the reference hands are seeded from the cards), cut into `n_buckets`.
Preflop uses the same percentile against random hands with no board... i.e. a cheap
equity-vs-random estimate, also seeded.
Actions: fold, check/call, raise to ~0.5 pot, ~1 pot, all-in ("F", "C", "H", "P", "A"),
filtered to what is legal and de-duplicated by amount.
Opponent bets that are not exactly an abstract size are mapped to the neighbouring sizes
with the pseudo-harmonic rule (Ganzfried & Sandholm): for x between sizes A < x < B (as pot
fractions), P(map to A) = (B - x)(1 + A) / ((B - A)(1 + x)).
"""
from __future__ import annotations

import zlib
from typing import Optional

import numpy as np

from bot.actions import Action, LegalActions, pot_fraction_raise

FRACTIONS = {"H": 0.5, "P": 1.0}
ORDER = ("F", "C", "H", "P", "A")


def abstract_actions(legal: LegalActions, pot: int, to_call: int, mybet: int) -> list[tuple[str, Action]]:
    """(label, concrete action) pairs for the abstract actions legal here."""
    out: list[tuple[str, Action]] = []
    if legal.fold:
        out.append(("F", Action.fold()))
    out.append(("C", Action.call() if legal.call else Action.check()))
    if legal.can_raise:
        seen = set()
        for label, frac in FRACTIONS.items():
            a = pot_fraction_raise(frac, pot, to_call, mybet, legal)
            if a is not None and a.amount not in seen:
                seen.add(a.amount)
                out.append((label, a))
        allin = Action.raise_to(legal.raise_max)  # type: ignore[arg-type]
        if allin.amount not in seen:
            out.append(("A", allin))
    return out


def raise_label(amount: int, pot_before: int, call_before: int, bet_before: int,
                rng: Optional[np.random.Generator] = None, all_in: bool = False) -> str:
    """Abstract label for an observed raise to `amount` (pseudo-harmonic between sizes)."""
    if all_in:
        return "A"
    denom = max(1, pot_before + call_before)
    x = (amount - bet_before - call_before) / denom          # the raise as a pot fraction
    sizes = sorted(FRACTIONS.items(), key=lambda kv: kv[1])
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
        ev = self.rules.evaluator
        seed = zlib.crc32(bytes(str((sorted(hole), sorted(board))), "ascii"))
        rng = np.random.default_rng(seed)
        dead = set(hole) | set(board)
        pool = np.array([c for c in self.rules.deck if c not in dead])
        k = len(hole)
        need = max(0, self.rules.board_cards - len(board))
        try:
            idx = np.argsort(rng.random((self.ref, len(pool))), axis=1)[:, :k + need]
            draw = pool[idx]
            full = np.concatenate([np.broadcast_to(np.array(board, dtype=np.intp), (self.ref, len(board))),
                                   draw[:, k:]], axis=1).astype(np.intp)
            mine = ev.evaluate_batch(np.broadcast_to(np.array(hole), (self.ref, k)), full)
            theirs = ev.evaluate_batch(draw[:, :k], full)
            eq = float(((mine > theirs) + 0.5 * (mine == theirs)).mean())
        except (ValueError, IndexError):
            eq = 0.5
        return min(self.n - 1, int(eq * self.n))


def infoset_key(player_street: int, bucket: int, history: str) -> str:
    return f"{player_street}|{bucket}|{history}"
