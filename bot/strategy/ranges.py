"""Our own range (Phase G): where does this hand rank among the hands we would have played this way?

"Defend by MDF" means continuing with the top slice of OUR range, not the top slice of all hands, so
the decision needs our hand's percentile inside the range our preflop line contains, on this board.
The line's contents are the per-class probabilities of the preflop table that produced it
(bot/strategy/preflop.py): the range is weighted by P(we took this action | hand class).

    OwnRange(evaluator, tables).percentile(hole, board, dead, class_weights, rng) -> float | None

Sample random 3-card hands from the unseen cards, weight them by `class_weights[class]`, let each keep the
two cards the usual rule keeps on the flop (bot/sim/discard.py: the best hand with the flop), score
them on the current board and count the weighted share of the range our hand beats (ties half).
1.0 = the top of our range, 0.0 = the bottom. None if the sample holds no weight.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from bot.equity import sample_without_replacement
from bot.sim.discard import opponent_keeps


class OwnRange:
    def __init__(self, evaluator, tables, deck: Sequence[int]) -> None:
        self.ev = evaluator
        self.tables = tables
        self.deck = np.array(sorted(deck), dtype=np.intp)

    def percentile(self, hole: Sequence[int], board: Sequence[int], dead: Sequence[int],
                   class_weights: Optional[np.ndarray], rng: np.random.Generator,
                   n: int = 300) -> Optional[float]:
        board = list(board)
        if len(board) < 3 or not hole:
            return None
        flop = np.array(board[:3], dtype=np.intp)
        board_np = np.array(board, dtype=np.intp)
        gone = set(board) | set(dead)
        pool = np.array([c for c in self.deck if c not in gone], dtype=np.intp)
        if len(pool) < 3:
            return None
        hands = sample_without_replacement(rng, pool, n, 3)
        if class_weights is None:
            w = np.ones(n)
        else:
            ids = self.tables.classes.class_batch(hands)
            w = np.asarray(class_weights, dtype=float)[ids]
        total = float(w.sum())
        if total <= 1e-9:
            return None
        kept = opponent_keeps(self.ev, hands, flop)
        values = self.ev.evaluate_batch(kept, board_np)
        mine_cards = list(hole)
        if len(mine_cards) == 3:
            mine_cards = [int(c) for c in opponent_keeps(self.ev, np.array([mine_cards], dtype=np.intp), flop)[0]]
        mine = int(self.ev.evaluate(mine_cards, board))
        return float((w * (values < mine)).sum() / total + 0.5 * (w * (values == mine)).sum() / total)
