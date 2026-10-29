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
