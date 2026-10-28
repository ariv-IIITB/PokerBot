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
"""

import time
from typing import List, Optional, Sequence, Tuple
import numpy as np

from preflop import TOTAL_COMBOS, COMBO_LIST
from evaluator import evaluate_7cards

ALL_CARDS = np.arange(52, dtype=np.int32)


def calculate_river_exact(
    hero_cards: Sequence[int],
    board: Sequence[int],
    villain_weights: np.ndarray,
    deadline: Optional[float] = None,
) -> Tuple[float, float]:
    """
    Exact enumeration of all legal opponent hole-card combinations on the river.
    Returns: (equity, sampling_uncertainty) -> uncertainty is 0.0 for exact enumeration.
    """
    dead_mask = 0
    for c in hero_cards:
        dead_mask |= (1 << c)
    for c in board:
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


def calculate_equity(
    hero_cards: Sequence[int],
    board: Sequence[int],
    villain_weights: np.ndarray,
    street: str,
    deadline: Optional[float] = None,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[float, float]:
    """
    Computes range-weighted equity using exact sampling specifications:
    - preflop: 256 samples
    - flop: 384 samples
    - turn: 512 samples
    - river: exact enumeration (with sampling fallback if tight deadline)
    
    Returns: (equity, sampling_uncertainty)
    where sampling_uncertainty = sqrt(E * (1 - E) / N)
    """
    if rng is None:
        rng = np.random.default_rng()

    b_len = len(board)

    # River exact enumeration
    if b_len == 5 or street == "river":
        # Check if enough time remains for exact river enumeration (requires ~1.5ms)
        if deadline is None or (deadline - time.monotonic()) > 0.003:
            return calculate_river_exact(hero_cards, board, villain_weights, deadline=deadline)

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

    dead_set = set(hero_cards) | set(board)
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
        return 0.5, 0.05

    prob_arr = np.array(valid_probs, dtype=np.float64)
    prob_sum = prob_arr.sum()
    if prob_sum <= 0.0:
        prob_arr.fill(1.0 / len(prob_arr))
    else:
        prob_arr /= prob_sum

    # Sample opponent combos weighted by w(h)
    chosen_combo_indices = rng.choice(valid_indices, size=target_samples, p=prob_arr)

    wins = 0.0
    ties = 0.0
    completed = 0

    hero_c1, hero_c2 = hero_cards
    board_list = list(board)
    deck_arr = np.array(deck, dtype=np.int32)

    for idx in chosen_combo_indices:
        if deadline is not None and (completed & 0x3F) == 0:
            if time.monotonic() >= deadline:
                break

        opp_c1, opp_c2 = COMBO_LIST[idx]

        if needed_board == 0:
            # River runout
            hero_7 = (hero_c1, hero_c2, board_list[0], board_list[1], board_list[2], board_list[3], board_list[4])
            opp_7 = (opp_c1, opp_c2, board_list[0], board_list[1], board_list[2], board_list[3], board_list[4])
        else:
            # Draw remaining community cards from deck excluding opp hole cards
            rem_deck = [c for c in deck_arr if c != opp_c1 and c != opp_c2]
            runout = rng.choice(rem_deck, size=needed_board, replace=False)
            full_board = board_list + list(runout)
            hero_7 = [hero_c1, hero_c2] + full_board
            opp_7 = [opp_c1, opp_c2] + full_board

        hero_score = evaluate_7cards(hero_7)
        opp_score = evaluate_7cards(opp_7)

        if hero_score > opp_score:
            wins += 1.0
        elif hero_score == opp_score:
            ties += 1.0
        completed += 1

    if completed == 0:
        return 0.5, 0.05

    equity = (wins + 0.5 * ties) / completed
    # Quantified sampling uncertainty margin: SE = sqrt(E * (1 - E) / N)
    variance = max(0.0, equity * (1.0 - equity))
    se = float(np.sqrt(variance / completed))

    return float(equity), se
