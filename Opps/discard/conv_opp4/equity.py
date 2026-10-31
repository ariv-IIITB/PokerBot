"""
equity.py - Range-weighted equity calculator with exact sample counts:
- 256 preflop samples
- 384 flop samples
- 512 turn samples
- Exact river enumeration (with bounded sampling fallback when deadline approaches)
- Dead card elimination from all 1,326 combos
- Proportional weighted sampling: w(h)
- Sampling uncertainty estimation: SE = sqrt(E * (1 - E) / N)
- Monotonic clock deadline enforcement

Discard Hold'em: before the discard the hero holds 3 hole cards and will keep 2 of them,
so a 3-card hand is valued as its best 2-card keep (all keeps are scored on the same sampled
opponent hands and runouts). Discarded cards (the hero's and the opponent's) are out of play.
"""

import time
from itertools import combinations
from typing import List, Optional, Sequence, Tuple
import numpy as np

from preflop import TOTAL_COMBOS, COMBO_LIST
from evaluator import evaluate_7cards

ALL_CARDS = np.arange(52, dtype=np.int32)


def keeps(hero_cards: Sequence[int]) -> List[Tuple[int, int]]:
    """The 2-card hands the hero can end up with."""
    cards = list(hero_cards)
    if len(cards) <= 2:
        return [tuple(cards)]
    return [tuple(k) for k in combinations(cards, 2)]


def calculate_river_exact(
    hero_cards: Sequence[int],
    board: Sequence[int],
    villain_weights: np.ndarray,
    deadline: Optional[float] = None,
    dead: Sequence[int] = (),
) -> Tuple[float, float]:
    """
    Exact enumeration of all legal opponent hole-card combinations on the river.
    Returns: (equity, sampling_uncertainty) -> uncertainty is 0.0 for exact enumeration.
    """
    dead_mask = 0
    for c in list(hero_cards) + list(board) + list(dead):
        dead_mask |= (1 << c)

    hero_7 = list(hero_cards) + list(board)
    hero_score = evaluate_7cards(hero_7)

    win_weight = 0.0
    tie_weight = 0.0
    total_weight = 0.0

    b0, b1, b2, b3, b4 = board

    for i in range(TOTAL_COMBOS):
        w = villain_weights[i]
        if w <= 1e-7:
            continue
        c1, c2 = COMBO_LIST[i]
        if (dead_mask & (1 << c1)) or (dead_mask & (1 << c2)):
            continue

        opp_score = evaluate_7cards((c1, c2, b0, b1, b2, b3, b4))
        if hero_score > opp_score:
            win_weight += w
        elif hero_score == opp_score:
            tie_weight += w
        total_weight += w

        if deadline is not None and (i & 0x7F) == 0:
            if time.monotonic() >= deadline:
                break

    if total_weight <= 0.0:
        return 0.5, 0.0
    equity = (win_weight + 0.5 * tie_weight) / total_weight
    return float(equity), 0.0


def calculate_keep_equities(
    hero_cards: Sequence[int],
    board: Sequence[int],
    villain_weights: np.ndarray,
    street: str,
    deadline: Optional[float] = None,
    rng: Optional[np.random.Generator] = None,
    dead: Sequence[int] = (),
) -> Tuple[List[Tuple[int, int]], List[float], int]:
    """
    Range-weighted equity of every 2-card keep of `hero_cards` on the same samples.
    Returns: (keeps, equity per keep, number of samples completed).
    Sample counts per street: 256 preflop, 384 flop, 512 turn, exact river enumeration.
    """
    if rng is None:
        rng = np.random.default_rng()

    options = keeps(hero_cards)
    b_len = len(board)

    # River exact enumeration
    if b_len == 5 or street == "river":
        if deadline is None or (deadline - time.monotonic()) > 0.003:
            eqs = [calculate_river_exact(k, board, villain_weights, deadline=deadline, dead=dead)[0]
                   for k in options]
            return options, eqs, 0

    # Determine sample count by street
    if b_len == 0 or street == "preflop":
        target_samples = 256
        needed_board = 5
    elif b_len == 3 or street == "flop":
        target_samples = 384
        needed_board = 2
    elif b_len == 4 or street == "turn":
        target_samples = 512
        needed_board = 1
    else:
        target_samples = 256
        needed_board = 0

    dead_set = set(hero_cards) | set(board) | set(dead)
    deck = [c for c in range(52) if c not in dead_set]

    # Filter legal opponent combinations and extract non-zero weights
    valid_indices: List[int] = []
    valid_probs: List[float] = []

    for i in range(TOTAL_COMBOS):
        w = villain_weights[i]
        if w <= 1e-7:
            continue
        c1, c2 = COMBO_LIST[i]
        if c1 in dead_set or c2 in dead_set:
            continue
        valid_indices.append(i)
        valid_probs.append(w)

    if not valid_indices:
        return options, [0.5] * len(options), 0

    prob_arr = np.array(valid_probs, dtype=np.float64)
    prob_sum = prob_arr.sum()
    if prob_sum <= 0.0:
        prob_arr.fill(1.0 / len(prob_arr))
    else:
        prob_arr /= prob_sum

    # Sample opponent combos weighted by w(h)
    chosen_combo_indices = rng.choice(valid_indices, size=target_samples, p=prob_arr)

    wins = [0.0] * len(options)
    ties = [0.0] * len(options)
    completed = 0

    board_list = list(board)
    deck_arr = np.array(deck, dtype=np.int32)

    for idx in chosen_combo_indices:
        if deadline is not None and (completed & 0x3F) == 0:
            if time.monotonic() >= deadline:
                break

        opp_c1, opp_c2 = COMBO_LIST[idx]

        if needed_board == 0:
            full_board = board_list
        else:
            # Draw remaining community cards from deck excluding opp hole cards
            rem_deck = [c for c in deck_arr if c != opp_c1 and c != opp_c2]
            runout = rng.choice(rem_deck, size=needed_board, replace=False)
            full_board = board_list + list(runout)

        opp_score = evaluate_7cards([opp_c1, opp_c2] + full_board)
        for k, keep in enumerate(options):
            hero_score = evaluate_7cards(list(keep) + full_board)
            if hero_score > opp_score:
                wins[k] += 1.0
            elif hero_score == opp_score:
                ties[k] += 1.0
        completed += 1

    if completed == 0:
        return options, [0.5] * len(options), 0

    eqs = [(wins[k] + 0.5 * ties[k]) / completed for k in range(len(options))]
    return options, eqs, completed


def calculate_equity(
    hero_cards: Sequence[int],
    board: Sequence[int],
    villain_weights: np.ndarray,
    street: str,
    deadline: Optional[float] = None,
    rng: Optional[np.random.Generator] = None,
    dead: Sequence[int] = (),
) -> Tuple[float, float]:
    """
    Computes range-weighted equity using exact sampling specifications:
    - preflop: 256 samples
    - flop: 384 samples
    - turn: 512 samples
    - river: exact enumeration (with sampling fallback if tight deadline)
    With 3 hole cards the equity is that of the best 2-card keep.

    Returns: (equity, sampling_uncertainty)
    where sampling_uncertainty = sqrt(E * (1 - E) / N)
    """
    options, eqs, completed = calculate_keep_equities(
        hero_cards, board, villain_weights, street, deadline, rng, dead)
    equity = max(eqs)
    if completed == 0:
        # exact river enumeration (se 0), or no usable samples
        if len(board) == 5 or street == "river":
            return float(equity), 0.0
        return float(equity), 0.05
    # Quantified sampling uncertainty margin: SE = sqrt(E * (1 - E) / N)
    variance = max(0.0, equity * (1.0 - equity))
    return float(equity), float(np.sqrt(variance / completed))
