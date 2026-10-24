"""Small statistics helpers for match results."""
from __future__ import annotations

import math
from typing import Sequence


def mean_se(xs: Sequence[float]) -> tuple[float, float]:
    """Mean and standard error of the mean (SE = 0 for fewer than 2 values)."""
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    m = sum(xs) / n
    if n < 2:
        return m, 0.0
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(var / n)


def win_rate(scores: Sequence[float]) -> tuple[float, float]:
    """Mean match score (win=1, draw=0.5) and its standard error."""
    return mean_se(list(scores))


def z_score(mean: float, se: float) -> float:
    return mean / se if se > 0 else (math.inf if mean > 0 else (-math.inf if mean < 0 else 0.0))


def fmt_pm(mean: float, se: float, digits: int = 3) -> str:
    return f"{mean:+.{digits}f} ± {se:.{digits}f}"
