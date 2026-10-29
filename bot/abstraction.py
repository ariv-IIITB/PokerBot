"""Abstraction: hand strength, buckets, abstract actions and the infoset key, written once.

Used by the bot (equity, inference) and by the lab's MCCFR trainer and CFR brain (lab/cfr/),
so the trainer and anything that plays its tables derive the same keys.

Showdown share: P(win) + 0.5 P(tie) of our hand vs opponent hands on full boards, from the
variant's scorer (rules.evaluator); every equity estimate is a mean of it.
Strength percentile: where a hand's value ranks among random hands on the same board.
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


def showdown_share(ev, mine: np.ndarray, theirs: np.ndarray, board: np.ndarray) -> np.ndarray:
    """Per row: 1 if our hand wins, 0.5 if it ties, 0 if it loses (rows of hole cards and
    full boards, as evaluate_batch takes them)."""
    a = ev.evaluate_batch(mine, board)
    b = ev.evaluate_batch(theirs, board)
    return (a > b) + 0.5 * (a == b)


def strength_percentile(ev, deck, holes: np.ndarray, board, n_ref: int, rng) -> np.ndarray:
    """For each row of `holes`: the fraction of `n_ref` random hands (from `deck` minus the
    known cards) it beats or ties on `board` right now. ValueError if it can't be scored."""
    vals = ev.evaluate_batch(holes, board)
    dead = set(board) | set(np.unique(holes).tolist())
    pool = np.array([c for c in deck if c not in dead])
    k = holes.shape[1]
    if len(pool) < k:
        raise ValueError("not enough cards for reference hands")
    idx = np.argsort(rng.random((n_ref, len(pool))), axis=1)[:, :k]
    ref = np.sort(ev.evaluate_batch(pool[idx], board))
    return np.searchsorted(ref, vals, side="right") / len(ref)


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
            eq = float(showdown_share(ev, np.broadcast_to(np.array(hole), (self.ref, k)),
                                      draw[:, :k], full).mean())
        except (ValueError, IndexError):
            eq = 0.5
        return min(self.n - 1, int(eq * self.n))


def label_of(action: Action, legal: LegalActions, pot: int, to_call: int, bet: int,
             all_in: bool = False, rng: Optional[np.random.Generator] = None,
             fractions: Optional[dict] = None) -> tuple[str, bool]:
    """(abstract label, translated?) of an observed action. A raise the abstraction could have
    made (same amount) gets that label, exactly as in training; any other raise is translated
    pseudo-harmonically."""
    if action.kind == "F":
        return "F", False
    if action.kind in ("C", "K"):
        return "C", False
    exact = [name for name, x in abstract_actions(legal, pot, to_call, bet, fractions)
             if x.kind == action.kind and x.amount == action.amount]
    if exact:
        return exact[0], False
    return raise_label(action.amount, pot, to_call, bet, rng, all_in, fractions), True


def extend_history(history: str, label: str, street_before: int, street_after: int) -> str:
    """The betting history after one more action: labels, "/" after the action that ends a
    street. Training (lab/cfr/abstract_game.py) and play (lab/cfr/brain.py) both build it here."""
    return history + label + ("/" if street_after != street_before else "")


def infoset_key(player_street: int, bucket: int, history: str) -> str:
    return f"{player_street}|{bucket}|{history}"
