"""Board texture and draw features (Phase G). Pure Python, no NumPy.

Cards are ints `rank * 4 + suit` (rank 0 = deuce .. 12 = ace, bot/cards.py). Everything works for
a flop, turn or river board and for 2 or 3 hole cards (3 = before the discard: the features of
the best 2-card keep are returned).

    board_texture(board) -> Texture   paired / trips / suit and rank structure and a 0..1 "wet" score
    draw_features(hole, board) -> Draws   made-pair type, flush and straight draws, backdoors, overcards
    best_keep(hole, board) -> (keep, Draws)   for 3 hole cards: the keep with the most to play for
    blocker_score(hole, board) -> float    how much of the opponent's strongest holdings we block

The numbers are heuristics for choosing bet sizes and bluff candidates, not equities.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

ACE = 12


def _rank(c: int) -> int:
    return c // 4


def _suit(c: int) -> int:
    return c % 4


def _windows():
    """The ten 5-rank straight windows as rank sets; the ace plays low (A-2-3-4-5) and high."""
    out = [frozenset({12, 0, 1, 2, 3})]
    out += [frozenset(range(lo, lo + 5)) for lo in range(9)]
    return out


WINDOWS = _windows()


@dataclass(frozen=True)
class Texture:
    n_cards: int
    paired: bool           # at least two cards of one rank
    trips: bool            # three or more of one rank
    suit_max: int          # most cards of one suit
    monotone: bool         # all board cards one suit (flop) / flush possible with any hole cards
    two_tone: bool         # exactly one suit has two cards on a flop; turn/river: suit_max == 3 with 4 cards...
    straight_window: int   # most distinct board ranks inside one five-rank straight window
    high: int              # highest board rank
    connected: bool        # three or more board ranks within a straight window
    wet: float             # 0 (dry) .. 1 (wet): how many draws and made-hand upgrades the board allows
    low_connected: bool    # low and connected: favours the player who called, not the raiser
    high_dry: bool         # ace/king/queen high and dry: favours the raiser


def board_texture(board: Sequence[int]) -> Texture:
    board = list(board)
    n = len(board)
    ranks = [_rank(c) for c in board]
    counts: dict[int, int] = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    suit_counts = [0, 0, 0, 0]
    for c in board:
        suit_counts[_suit(c)] += 1
    suit_max = max(suit_counts) if n else 0
    paired = any(v >= 2 for v in counts.values())
    trips = any(v >= 3 for v in counts.values())
    distinct = set(ranks)
    window = max((len(distinct & w) for w in WINDOWS), default=0)
    high = max(ranks) if ranks else 0
    monotone = n >= 3 and suit_max == n
    two_tone = n >= 3 and suit_max == 2
    connected = window >= 3

    # flush potential: three to a suit is a flush draw for anyone with two of it, two to a suit a backdoor
    if suit_max >= 4:
        flush_pot = 0.8
    elif suit_max == 3:
        flush_pot = 0.5 if n == 3 else 0.45
    elif suit_max == 2:
        flush_pot = 0.2 if n == 3 else 0.1
    else:
        flush_pot = 0.0
    # straight potential: how many board ranks sit in one window (more = more draws and made straights)
    if window >= 5:
        straight_pot = 0.9
    elif window == 4:
        straight_pot = 0.6
    elif window == 3:
        straight_pot = 0.4 if n == 3 else 0.35
    elif window == 2:
        straight_pot = 0.15 if n == 3 else 0.1
    else:
        straight_pot = 0.0
    wet = flush_pot + straight_pot - (0.15 if paired else 0.0)
    wet = min(1.0, max(0.0, wet))
    low_connected = n >= 3 and high <= 7 and (window >= 3 or monotone)       # nine-high or lower
    high_dry = n >= 3 and high >= 10 and wet < 0.4                          # queen-high or better
    return Texture(n, paired, trips, suit_max, monotone, two_tone, window, high, connected,
                   wet, low_connected, high_dry)


@dataclass(frozen=True)
class Draws:
    pair_type: str         # none | under | third | second | top | overpair | two_pair | set_plus
    flush_draw: int        # 0 none, 1 = one hole card in the suit (needs 3 on board), 2 = both hole cards
    nut_flush_draw: bool
    backdoor_flush: bool   # flop only: two hole cards of a suit with one on the board
    straight_outs: int     # distinct ranks that complete a straight using one of our hole cards
    backdoor_straight: bool
    overcards: int         # hole cards above the highest board rank
    made_straight_or_better: bool

    @property
    def outs_class(self) -> str:
        """'strong' (a flush draw or an open-ended straight draw: 8+ outs), 'gutshot' (4 outs),
        'backdoor', 'none'. On the river these describe a MISSED draw (nothing left to come)."""
        if self.flush_draw >= 1 or self.straight_outs >= 2:
            return "strong"
        if self.straight_outs == 1:
            return "gutshot"
        if self.backdoor_flush or self.backdoor_straight:
            return "backdoor"
        return "none"

    @property
    def has_showdown_value(self) -> bool:
        return self.pair_type not in ("none", "under")


def _straight_completions(ranks: set[int], hole_ranks: set[int]) -> int:
    """Ranks x not yet present such that ranks+{x} contains a five-window using a hole rank."""
    outs = 0
    for x in range(13):
        if x in ranks:
            continue
        new = ranks | {x}
        if any(w <= new and (w & hole_ranks) and x in w for w in WINDOWS):
            outs += 1
    return outs


def draw_features(hole: Sequence[int], board: Sequence[int]) -> Draws:
    """Features of exactly two hole cards on `board` (see best_keep for three)."""
    hole, board = list(hole), list(board)
    hr = [_rank(c) for c in hole]
    br = [_rank(c) for c in board]
    n = len(board)
    allr = hr + br
    counts: dict[int, int] = {}
    for r in allr:
        counts[r] = counts.get(r, 0) + 1
    board_counts: dict[int, int] = {}
    for r in br:
        board_counts[r] = board_counts.get(r, 0) + 1
    # made pair types, counting only pairs that use a hole card
    pair_type = "none"
    if any(counts.get(r, 0) >= 3 for r in hr):
        pair_type = "set_plus"
    else:
        used = [r for r in set(hr) if counts[r] >= 2]       # hole ranks that pair something
        pocket = len(hr) == 2 and hr[0] == hr[1]
        if len(used) >= 2:
            pair_type = "two_pair"
        elif used:
            r = used[0]
            higher = len({b for b in br if b > r})           # board ranks above our pair
            if pocket and higher == 0:
                pair_type = "overpair"
            else:
                pair_type = ("top", "second", "third")[higher] if higher < 3 else "under"
    suits = [_suit(c) for c in hole + board]
    suit_counts = [0, 0, 0, 0]
    for s in suits:
        suit_counts[s] += 1
    hole_suit = [0, 0, 0, 0]
    for c in hole:
        hole_suit[_suit(c)] += 1
    flush_draw = 0
    nut = False
    for s in range(4):
        if suit_counts[s] == 4 and hole_suit[s] >= 1:
            flush_draw = max(flush_draw, 2 if hole_suit[s] == 2 else 1)
            if any(_suit(c) == s and _rank(c) == ACE for c in hole):
                nut = True
    backdoor_flush = n == 3 and any(hole_suit[s] == 2 and suit_counts[s] == 3 for s in range(4))

    rank_set = set(allr)
    hole_set = set(hr)
    made_straight = any(w <= rank_set and (w & hole_set) for w in WINDOWS)
    outs = 0 if made_straight else _straight_completions(rank_set, hole_set)
    backdoor_straight = False
    if n == 3 and not made_straight and outs == 0:
        backdoor_straight = any(len(w & rank_set) >= 3 and (w & hole_set) for w in WINDOWS)
    top = max(br, default=-1)
    overcards = sum(1 for r in hr if r > top)
    flush_made = any(suit_counts[s] >= 5 and hole_suit[s] >= 1 for s in range(4))
    return Draws(pair_type, 0 if flush_made else flush_draw, nut and not flush_made, backdoor_flush,
                 outs, backdoor_straight, overcards, made_straight or flush_made)


_PAIR_SCORE = {"none": 0, "under": 1, "third": 2, "second": 3, "top": 4, "overpair": 5,
               "two_pair": 6, "set_plus": 7}


def _keep_score(d: Draws) -> float:
    s = _PAIR_SCORE[d.pair_type] * 2.0 + (10.0 if d.made_straight_or_better else 0.0)
    s += {"strong": 3.0, "gutshot": 1.0, "backdoor": 0.4, "none": 0.0}[d.outs_class]
    s += 0.3 * d.overcards
    return s


def best_keep(hole: Sequence[int], board: Sequence[int]) -> tuple[tuple[int, ...], Draws]:
    """For 2 or 3 hole cards: the keep (2 cards) with the best made hand and draws on `board`."""
    hole = list(hole)
    if len(hole) <= 2:
        return tuple(hole), draw_features(hole, board)
    best = None
    for keep in combinations(hole, 2):
        d = draw_features(keep, board)
        sc = (_keep_score(d), sum(_rank(c) for c in keep))
        if best is None or sc > best[0]:
            best = (sc, keep, d)
    return tuple(best[1]), best[2]  # type: ignore[index]


def blocker_score(hole: Sequence[int], board: Sequence[int]) -> float:
    """0..1: how much we hold of what the opponent needs to call a bluff-catching bet: the ace
    or other high card of a flush suit that is three or more on the board, and the top board
    ranks. Used to pick which hands without showdown value bluff."""
    hole, board = list(hole), list(board)
    score = 0.0
    suit_counts = [0, 0, 0, 0]
    for c in board:
        suit_counts[_suit(c)] += 1
    for c in hole:
        if suit_counts[_suit(c)] >= 3:
            score = max(score, 1.0 if _rank(c) == ACE else (0.7 if _rank(c) >= 10 else 0.35))
    top = sorted({_rank(c) for c in board}, reverse=True)[:2]
    for c in hole:
        if _rank(c) in top:
            score = max(score, 0.5)
        elif _rank(c) == ACE:
            score = max(score, 0.4)
    return score
