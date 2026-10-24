"""★ Variant hook: which hand evaluator the bot, equity engine and lab engine use. ★

Default: the generic best-k-of-N evaluator configured from GameConfig. If the variant has
unusual hand rankings (e.g. 3-card hands where a straight beats a flush, wild cards,
lowball), write an evaluator with the same two methods and return it here:

    evaluate(hole, board) -> int                         (higher wins, equal = split)
    evaluate_batch(hole (B,h), board (B,b)) -> ndarray (B,)
"""
from __future__ import annotations

from typing import Protocol, Sequence

import numpy as np

from bot.evaluator import GenericEvaluator
from variant.rules import DEFAULT_CONFIG, GameConfig


class Evaluator(Protocol):
    def evaluate(self, hole: Sequence[int], board: Sequence[int]) -> int: ...

    def evaluate_batch(self, hole: np.ndarray, board: np.ndarray) -> np.ndarray: ...


def make_evaluator(config: GameConfig = DEFAULT_CONFIG) -> Evaluator:
    return GenericEvaluator(config.hand_size, config.hole_cards_used)
