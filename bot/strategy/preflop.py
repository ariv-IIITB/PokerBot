"""Phase G preflop for 3-card hands: strength, playability and the action tables of the Ivey style.

Everything is built from the precomputed 3-card class table (bot/sim/tables.py): the class's
equity vs a random hand (the best 2 after the discard is part of that number) gives STRENGTH; a
PLAYABILITY score computed from the cards (the best suited pair among the three, connectedness, a
pair, an ace with a suited card, three cards that work together) says how well the hand plays after
the flop. Hand names are never translated by hand. The two are blended into one percentile
(`c_pct`, 1 = best), and each spot is a table with the probability of [fold, passive, raise] for
every class, so decisions are mixed rather than cut off at an edge, and the same table says which
hands our preflop line contains (bot/strategy/ranges.py uses it as our own range).

Spots (positions are heads-up: the button posts the small blind and acts first preflop):
    btn_open      button, first to act            fold / limp (passive) / raise
    bb_vs_limp    big blind, the button limped    (fold never) check (passive) / raise
    bb_vs_open    facing a raise to x big blinds  fold / call (passive) / 3-bet
    btn_vs_3bet   we opened, they re-raised       fold / call (passive) / 4-bet
Anything else returns no spot and the caller falls back to Tier 2.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional, Sequence

import numpy as np

from bot.actions import CALL, RAISE
from bot.cards import rank_of, suit_of
from bot.state import ME, OPP

FOLD_COL, PASSIVE_COL, RAISE_COL = 0, 1, 2


# --------------------------------------------------------------------------- blends

def blend_above(x: np.ndarray, cut: float, band: float) -> np.ndarray:
    """0 well below `cut`, 1 well above, linear over a band of width `band` around it."""
    if band <= 0:
        return (x >= cut).astype(float)
    return np.clip((x - (cut - band / 2)) / band, 0.0, 1.0)


def blend_below(x: np.ndarray, cut: float, band: float) -> np.ndarray:
    return 1.0 - blend_above(x, cut, band)


# --------------------------------------------------------------------------- features

def keep_playability(a: int, b: int) -> float:
    """How well the two cards play after the flop, 0..1 (suitedness, connectedness, pairs, ace)."""
    ra, rb = rank_of(a), rank_of(b)
    hi, lo = max(ra, rb), min(ra, rb)
    if ra == rb:
        return 0.45 + 0.4 * ra / 12                       # set mining grows with the pair
    suited = suit_of(a) == suit_of(b)
    gap = hi - lo - 1
    conn = {0: 1.0, 1: 0.7, 2: 0.4, 3: 0.15}.get(gap, 0.0)
    if hi == 12 and lo <= 3:
        conn = max(conn, 0.4)                             # the wheel: A-2 .. A-5 work with a low straight
    v = 0.40 * suited + 0.35 * conn + 0.25 * hi / 12
    if hi == 12 and suited:
        v += 0.15                                         # nut flush draws and blockers
    return min(1.0, v)


def playability(hole: Sequence[int]) -> float:
    """Playability of a 3-card hand: its best 2-card keep, plus a little for three cards that
    work together (all one suit, or three ranks inside one straight window)."""
    hole = list(hole)
    best = max(keep_playability(a, b) for a, b in combinations(hole, 2))
    flex = 0.0
    if len(hole) == 3:
        if len({suit_of(c) for c in hole}) == 1:
            flex = 1.0
        ranks = sorted({rank_of(c) for c in hole})
        if len(ranks) == 3 and ranks[-1] - ranks[0] <= 4:
            flex = max(flex, 0.8)
    return min(1.0, best + 0.1 * flex)


def blocker_value(hole: Sequence[int]) -> float:
    """What we block of the opponent's strongest hands: an ace (more if it is suited with another
    of our cards: the nut flush draw's blocker), a king."""
    ranks = [rank_of(c) for c in hole]
    v = 0.0
    if 12 in ranks:
        ace = [c for c in hole if rank_of(c) == 12][0]
        v = 1.0 if any(suit_of(c) == suit_of(ace) for c in hole if c != ace) else 0.85
    elif 11 in ranks:
        v = 0.4
    return v


def bluff_score(hole: Sequence[int]) -> float:
    return 0.7 * blocker_value(hole) + 0.3 * playability(hole)


def weighted_percentile(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Percentile of every entry among the weighted population (ties count half), 0..1."""
    uniq, inv = np.unique(values, return_inverse=True)
    mass = np.bincount(inv, weights=weights)
    cum = np.cumsum(mass) - mass
    return ((cum + 0.5 * mass) / mass.sum())[inv]


# --------------------------------------------------------------------------- the model

class PreflopModel:
    """Per-class strength, playability and combined percentile for the active 3-card tables."""

    def __init__(self, tables, play_weight: float = 0.35) -> None:
        self.tables = tables
        deck = tables.classes.deck
        tab = np.asarray(tables.classes.table)
        n = int(tab.max()) + 1
        self.n = n
        self.counts = np.bincount(tab, minlength=n).astype(float)
        self.total = self.counts.sum()
        _, first = np.unique(tab, return_index=True)
        combos = list(combinations(deck, 3))
        self.reps = [combos[i] for i in first]            # one hand of every class
        self.s_pct = weighted_percentile(np.asarray(tables.eq_random, dtype=float), self.counts)
        self.play = np.array([playability(r) for r in self.reps])
        self.bluff = np.array([bluff_score(r) for r in self.reps])
        mean_play = float((self.play * self.counts).sum() / self.total)
        self.c_pct = weighted_percentile(self.s_pct + play_weight * (self.play - mean_play), self.counts)
        self._cache: dict = {}

    def class_of(self, hole: Sequence[int]) -> int:
        return self.tables.classes.class_of(list(hole))

    def probs(self, key: tuple, build) -> np.ndarray:
        """Cache of (n, 3) tables by a hashable key."""
        arr = self._cache.get(key)
        if arr is None:
            arr = self._cache[key] = build()
        return arr

    # ---- reraise machinery shared by the 3-bet and 4-bet spots
    def reraise_table(self, defend: float, value_top: float, bluff_mass: float, band: float,
                      margin: float = 0.12) -> np.ndarray:
        """[fold, call, raise] where we continue with the top `defend` share, re-raise the top
        `value_top` for value plus `bluff_mass` of all hands as bluffs: the hands with the best
        blockers and playability among those near or just under the calling cut."""
        c = self.c_pct
        raise_val = blend_above(c, 1.0 - value_top, band)
        raise_blf = np.zeros(self.n)
        cand = np.nonzero((c >= 1.0 - defend - margin) & (raise_val < 0.5))[0]
        if len(cand) and bluff_mass > 0:
            order = cand[np.argsort(-self.bluff[cand], kind="stable")]
            left = bluff_mass * self.total
            for i in order:
                take = min(1.0, left / self.counts[i])
                raise_blf[i] = take
                left -= take * self.counts[i]
                if left <= 1e-9:
                    break
        p_raise = np.clip(raise_val + raise_blf, 0.0, 1.0)
        p_defend = blend_above(c, 1.0 - defend, band)
        p_call = np.clip(p_defend - p_raise, 0.0, 1.0)
        p_fold = np.clip(1.0 - p_call - p_raise, 0.0, 1.0)
        return np.stack([p_fold, p_call, p_raise], axis=1)

    # ---- the spots
    def btn_open(self, fold: float, limp: float, trap_zone: float, trap_prob: float,
                 band: float) -> np.ndarray:
        """Button first in: fold the bottom `fold`, limp the next `limp`, raise the rest; a few
        of the very best hands limp as traps."""
        c = self.c_pct
        p_fold = blend_below(c, fold, band)
        p_raise = blend_above(c, fold + limp, band)
        p_limp = np.clip(1.0 - p_fold - p_raise, 0.0, 1.0)
        trap = trap_prob * (self.s_pct >= 1.0 - trap_zone)
        p_limp = np.clip(p_limp + trap * p_raise, 0.0, 1.0)
        p_raise = p_raise * (1.0 - trap)
        return np.stack([p_fold, p_limp, p_raise], axis=1)

    def bb_vs_limp(self, raise_share: float, band: float) -> np.ndarray:
        p_raise = blend_above(self.c_pct, 1.0 - raise_share, band)
        return np.stack([np.zeros(self.n), 1.0 - p_raise, p_raise], axis=1)

    def bb_vs_open(self, defend: float, value_top: float, three_bet: float, band: float) -> np.ndarray:
        return self.reraise_table(defend, value_top, max(0.0, three_bet - value_top), band)

    def btn_vs_3bet(self, cont: float, value_top: float, four_bet: float, band: float) -> np.ndarray:
        return self.reraise_table(cont, value_top, max(0.0, four_bet - value_top), band)


# --------------------------------------------------------------------------- spot detection

@dataclass(frozen=True)
class Spot:
    name: str              # btn_open | bb_vs_limp | bb_vs_open | btn_vs_3bet
    raise_to_bb: float = 0.0   # the opponent's last raise, in big blinds (bb_vs_open, btn_vs_3bet)
    ratio: float = 0.0         # btn_vs_3bet: their raise as a multiple of our open


def preflop_spot(hand, bb: int) -> Optional[Spot]:
    """Which of the four supported spots this preflop decision is, from the hand's history.
    `hand` is a bot.state.HandState. None = not one of them (Tier 2 decides)."""
    if hand.street != 0 or bb <= 0:
        return None
    recs = [r for r in hand.history if r.street == 0]
    kinds = [(r.actor, r.action.kind) for r in recs]
    button = hand.seat == 0
    if button:
        if not recs:
            return Spot("btn_open")
        if kinds == [(ME, RAISE), (OPP, RAISE)]:
            ours = recs[0].action.amount or 0
            theirs = hand.opp_bet or (recs[1].action.amount or 0)
            return Spot("btn_vs_3bet", theirs / bb, theirs / ours if ours else 0.0)
        if kinds == [(ME, CALL), (OPP, RAISE)]:          # we limped and the big blind raised
            theirs = hand.opp_bet or (recs[1].action.amount or 0)
            return Spot("bb_vs_open", theirs / bb)
        return None
    if kinds == [(OPP, CALL)]:
        return Spot("bb_vs_limp")
    if kinds == [(OPP, RAISE)]:
        theirs = hand.opp_bet or (recs[0].action.amount or 0)
        return Spot("bb_vs_open", theirs / bb)
    return None
