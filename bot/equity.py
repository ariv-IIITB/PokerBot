"""Monte Carlo equity against a uniformly random opponent hand.

equity = P(win) + 0.5 * P(tie), estimated by dealing random opponent hole cards and a
random completion of the board, then comparing best hands. Card counts come from
the config (compiled Rules or a VariantSpec; default plain Hold'em: hole cards, board size,
deck, evaluator), so
this works for any variant whose showdown is "best hand wins".

Two implementations:
  * equity_scalar     - plain Python loop (simple reference, low overhead for tiny runs)
  * equity_vectorized - NumPy batches (fast); used by `equity()`
Both stop early when `time_budget_s` runs out and report how many samples they used.
`equity_exact` enumerates every possibility (small spots only, used to check accuracy).
"""
from __future__ import annotations

import itertools
import math
import random
import time
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

import numpy as np

from bot.game.rules_spec import to_rules


class Evaluator(Protocol):
    """What equity needs from a hand evaluator (higher wins, equal = split)."""
    def evaluate(self, hole: Sequence[int], board: Sequence[int]) -> int: ...

    def evaluate_batch(self, hole: np.ndarray, board: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class EquityResult:
    equity: float
    samples: int
    stderr: float       # standard error of the estimate (0 for exact)


def _setup(hole, board, config, evaluator, dead, opp_cards=None, runout=None):
    config = to_rules(config)
    ev = evaluator if evaluator is not None else config.evaluator
    known = set(hole) | set(board) | set(dead)
    deck = [c for c in config.deck if c not in known]
    n_opp = config.hole_cards if opp_cards is None else opp_cards
    n_run = config.board_cards - len(board) if runout is None else runout
    if n_run < 0:
        raise ValueError("board longer than the variant allows")
    if n_opp + n_run > len(deck):
        raise ValueError("not enough cards left to deal")
    return ev, deck, n_opp, n_run


def _result(total: float, total_sq: float, n: int) -> EquityResult:
    if n == 0:
        return EquityResult(0.5, 0, 0.5)
    mean = total / n
    var = max(0.0, total_sq / n - mean * mean)
    return EquityResult(mean, n, math.sqrt(var / n) if n > 1 else 0.5)


# --------------------------------------------------------------------------- scalar

def equity_scalar(hole: Sequence[int], board: Sequence[int],
                  config=None, evaluator: Optional[Evaluator] = None,
                  *, time_budget_s: Optional[float] = None, max_samples: int = 2000,
                  rng: Optional[np.random.Generator] = None, dead: Sequence[int] = (),
                  opp_cards: Optional[int] = None, runout: Optional[int] = None) -> EquityResult:
    """Pure-Python Monte Carlo. Checks the clock every 32 samples."""
    ev, deck, n_opp, n_run = _setup(hole, board, config, evaluator, dead, opp_cards, runout)
    rng = rng if rng is not None else np.random.default_rng()
    pyrng = random.Random(int(rng.integers(2**62)))
    hole, board = list(hole), list(board)
    deadline = None if time_budget_s is None else time.perf_counter() + time_budget_s
    total = total_sq = 0.0
    n = 0
    while n < max_samples:
        if deadline is not None and n % 32 == 0 and n > 0 and time.perf_counter() > deadline:
            break
        draw = pyrng.sample(deck, n_opp + n_run)
        full = board + draw[n_opp:]
        mine, theirs = ev.evaluate(hole, full), ev.evaluate(draw[:n_opp], full)
        s = 1.0 if mine > theirs else (0.5 if mine == theirs else 0.0)
        total += s
        total_sq += s * s
        n += 1
    return _result(total, total_sq, n)


# --------------------------------------------------------------------------- vectorized

def sample_without_replacement(rng: np.random.Generator, deck: np.ndarray, n: int,
                               k: int) -> np.ndarray:
    """n independent draws of k distinct cards from `deck` -> (n, k) array.
    Partial Fisher-Yates done column by column for all rows at once."""
    d = len(deck)
    perm = np.broadcast_to(np.arange(d), (n, d)).copy()
    rows = np.arange(n)
    for j in range(k):
        r = j + (rng.random(n) * (d - j)).astype(np.intp)
        a = perm[rows, j].copy()
        perm[rows, j] = perm[rows, r]
        perm[rows, r] = a
    return deck[perm[:, :k]]


def _score_batch(ev, hole, board, deck_np, n_opp, n_run, rng, n) -> np.ndarray:
    draw = sample_without_replacement(rng, deck_np, n, n_opp + n_run)
    if n_run:
        full = np.concatenate([np.broadcast_to(board, (n, len(board))), draw[:, n_opp:]], axis=1)
    else:
        full = np.broadcast_to(board, (n, len(board)))
    mine = ev.evaluate_batch(np.broadcast_to(hole, (n, len(hole))), full)
    theirs = ev.evaluate_batch(draw[:, :n_opp], full)
    return (mine > theirs) + 0.5 * (mine == theirs)


def equity_vectorized(hole: Sequence[int], board: Sequence[int],
                      config=None, evaluator: Optional[Evaluator] = None,
                      *, time_budget_s: Optional[float] = None, max_samples: int = 20000,
                      rng: Optional[np.random.Generator] = None, dead: Sequence[int] = (),
                      first_chunk: int = 128, max_chunk: int = 4096,
                      opp_cards: Optional[int] = None, runout: Optional[int] = None) -> EquityResult:
    """NumPy Monte Carlo in chunks. The first chunk measures speed; later chunks are sized
    to fit the remaining budget, so the deadline is overshot by at most ~one small chunk.
    opp_cards / runout override the opponent's hole-card count and the number of board
    cards still to come (defaults: from the rules)."""
    ev, deck, n_opp, n_run = _setup(hole, board, config, evaluator, dead, opp_cards, runout)
    rng = rng if rng is not None else np.random.default_rng()
    hole_np = np.asarray(hole, dtype=np.intp)
    board_np = np.asarray(board, dtype=np.intp)
    deck_np = np.asarray(deck, dtype=np.intp)
    t0 = time.perf_counter()
    total = total_sq = 0.0
    n = 0
    chunk = min(first_chunk, max_samples)
    while n < max_samples and chunk > 0:
        s = _score_batch(ev, hole_np, board_np, deck_np, n_opp, n_run, rng, chunk)
        total += float(s.sum())
        total_sq += float((s * s).sum())
        n += chunk
        if time_budget_s is None:
            chunk = min(max_chunk, max_samples - n)
            continue
        elapsed = time.perf_counter() - t0
        left = time_budget_s - elapsed
        if left <= 0:
            break
        rate = n / max(elapsed, 1e-9)                       # samples per second so far
        chunk = int(min(max_chunk, max_samples - n, rate * left * 0.8))
        if chunk < 16:
            break
    return _result(total, total_sq, n)


def equity(hole: Sequence[int], board: Sequence[int], config=None,
           evaluator: Optional[Evaluator] = None, **kw) -> EquityResult:
    """Default entry point (vectorized)."""
    return equity_vectorized(hole, board, config, evaluator, **kw)


# --------------------------------------------------------------------------- exact

def equity_exact(hole: Sequence[int], board: Sequence[int],
                 config=None, evaluator: Optional[Evaluator] = None,
                 dead: Sequence[int] = (), max_cases: int = 3_000_000,
                 opp_cards: Optional[int] = None, runout: Optional[int] = None) -> EquityResult:
    """Enumerate every opponent hand and board completion (small spots only)."""
    ev, deck, n_opp, n_run = _setup(hole, board, config, evaluator, dead, opp_cards, runout)
    cases = math.comb(len(deck), n_opp) * math.comb(len(deck) - n_opp, n_run)
    if cases > max_cases:
        raise ValueError(f"{cases} cases is too many to enumerate")
    opp_l, run_l = [], []
    for opp in itertools.combinations(deck, n_opp):
        rest = [c for c in deck if c not in opp]
        for run in itertools.combinations(rest, n_run):
            opp_l.append(opp)
            run_l.append(run)
    opp_a = np.array(opp_l, dtype=np.intp).reshape(len(opp_l), n_opp)
    run_a = np.array(run_l, dtype=np.intp).reshape(len(run_l), n_run)
    m = len(opp_a)
    full = np.concatenate([np.broadcast_to(np.asarray(board, dtype=np.intp), (m, len(board))),
                           run_a], axis=1)
    mine = ev.evaluate_batch(np.broadcast_to(np.asarray(hole, dtype=np.intp), (m, len(hole))), full)
    theirs = ev.evaluate_batch(opp_a, full)
    return EquityResult(float(((mine > theirs) + 0.5 * (mine == theirs)).mean()), m, 0.0)
