"""Pot-odds arithmetic for betting strategy (Phase G). Pure functions, no state.

All sizes are chips; `pot` is the pot BEFORE the bet in question.

    required_fold(bet, pot)  how often a bet must work to break even as a pure bluff
    mdf(bet, pot)            minimum defence frequency: the share of its range the defender must
                             continue with so that bluffs cannot profit automatically
    bluff_share(bet, pot)    the share of the bettor's range that can be bluffs so the caller is
                             indifferent (bluffs / (bluffs + value))
    spr(stack, pot)          stack-to-pot ratio

(Named potmath, not math, so the stdlib module can never be shadowed.)
"""
from __future__ import annotations


def required_fold(bet: float, pot: float) -> float:
    """bet / (pot + bet): a bluff of `bet` into `pot` needs this fold frequency."""
    total = pot + bet
    return bet / total if total > 0 else 0.0


def mdf(bet: float, pot: float) -> float:
    """pot / (pot + bet): the defender continues at least this often."""
    total = pot + bet
    return pot / total if total > 0 else 1.0


def bluff_share(bet: float, pot: float) -> float:
    """bet / (pot + 2 * bet): the bluff share of a balanced betting range."""
    total = pot + 2 * bet
    return bet / total if total > 0 else 0.0


def spr(stack: float, pot: float) -> float:
    """Effective stack behind divided by the pot (inf if the pot is empty)."""
    return stack / pot if pot > 0 else float("inf")
