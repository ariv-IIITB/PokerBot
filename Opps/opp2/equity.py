"""
equity.py - Range-weighted equity calculator with PPOT/NPOT and EHS calculation.
"""

from typing import List, Optional, Sequence, Tuple
import numpy as np
from evaluator import evaluate_7cards

ALL_CARDS = np.arange(52, dtype=np.int32)

COMBO_LIST: List[Tuple[int, int]] = []
COMBO_INDEX = np.full((52, 52), -1, dtype=np.int32)
for _c1 in range(52):
    for _c2 in range(_c1 + 1, 52):
        idx = len(COMBO_LIST)
        COMBO_LIST.append((_c1, _c2))
        COMBO_INDEX[_c1, _c2] = idx
        COMBO_INDEX[_c2, _c1] = idx

TOTAL_COMBOS = len(COMBO_LIST)


def calculate_river_exact(
    hero_cards: Sequence[int],
    board: Sequence[int],
    villain_weights: np.ndarray,
) -> float:
    dead_mask = 0
    for c in hero_cards:
        dead_mask |= 1 << c
    for c in board:
        dead_mask |= 1 << c

    hero_7 = list(hero_cards) + list(board)
    hero_score = evaluate_7cards(hero_7)

    win_weight = 0.0
    tie_weight = 0.0
    total_weight = 0.0

    b0, b1, b2, b3, b4 = board

    for i in range(TOTAL_COMBOS):
        w = villain_weights[i]
        if w <= 1e-6:
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

    if total_weight <= 0.0:
        return 0.5
    return (win_weight + 0.5 * tie_weight) / total_weight


def calculate_equity_mc(
    hero_cards: Sequence[int],
    board: Sequence[int],
    villain_weights: np.ndarray,
    n_rollouts: int = 350,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[float, float, float]:
    if rng is None:
        rng = np.random.default_rng()

    dead_set = set(hero_cards) | set(board)
    deck = np.array([c for c in range(52) if c not in dead_set], dtype=np.int32)
    deck_len = len(deck)

    valid_indices = []
    valid_probs = []
    for i in range(TOTAL_COMBOS):
        w = villain_weights[i]
        if w <= 1e-6:
            continue
        c1, c2 = COMBO_LIST[i]
        if c1 in dead_set or c2 in dead_set:
            continue
        valid_indices.append(i)
        valid_probs.append(w)

    if not valid_indices:
        return 0.5, 0.0, 0.5

    prob_arr = np.array(valid_probs, dtype=np.float64)
    total_p = prob_arr.sum()
    if total_p <= 0.0:
        prob_arr.fill(1.0 / len(prob_arr))
    else:
        prob_arr /= total_p

    cards_needed = 5 - len(board)
    if cards_needed == 0:
        eq = calculate_river_exact(hero_cards, board, villain_weights)
        return eq, 0.0, eq

    sampled_combo_idxs = rng.choice(valid_indices, size=n_rollouts, p=prob_arr)

    ahead = 0
    tied = 0
    behind = 0
    ahead_to_behind = 0
    behind_to_ahead = 0

    h1, h2 = hero_cards
    board_tuple = tuple(board)

    for i in range(n_rollouts):
        vc1, vc2 = COMBO_LIST[sampled_combo_idxs[i]]

        if len(board) == 3:
            curr_hero_score = evaluate_7cards((h1, h2, board[0], board[1], board[2], 0, 0))
            curr_opp_score = evaluate_7cards((vc1, vc2, board[0], board[1], board[2], 0, 0))
        elif len(board) == 4:
            curr_hero_score = evaluate_7cards((h1, h2, board[0], board[1], board[2], board[3], 0))
            curr_opp_score = evaluate_7cards((vc1, vc2, board[0], board[1], board[2], board[3], 0))
        else:
            curr_hero_score = curr_opp_score = 0

        runout: List[int] = []
        while len(runout) < cards_needed:
            c = deck[rng.integers(0, deck_len)]
            if c != vc1 and c != vc2 and c not in runout:
                runout.append(c)

        final_board = board_tuple + tuple(runout)
        final_hero = evaluate_7cards((h1, h2, *final_board))
        final_opp = evaluate_7cards((vc1, vc2, *final_board))

        was_ahead = curr_hero_score > curr_opp_score
        was_behind = curr_hero_score < curr_opp_score

        if final_hero > final_opp:
            ahead += 1
            if was_behind:
                behind_to_ahead += 1
        elif final_hero == final_opp:
            tied += 1
        else:
            behind += 1
            if was_ahead:
                ahead_to_behind += 1

    equity = (ahead + 0.5 * tied) / max(1, n_rollouts)
    ppot = behind_to_ahead / max(1, behind) if behind > 0 else 0.0
    npot = ahead_to_behind / max(1, ahead) if ahead > 0 else 0.0

    ehs = equity * (1.0 - npot) + (1.0 - equity) * ppot
    return float(np.clip(equity, 0.0, 1.0)), float(ppot), float(np.clip(ehs, 0.0, 1.0))
