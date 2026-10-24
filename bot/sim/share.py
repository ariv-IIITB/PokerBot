"""Expected showdown share: the generalization of equity to any scoring.

share = E[fraction of the pot we win at showdown], with both players checking down from
here. Ties, hi-lo halves, several boards, wild cards and short decks all come out of the
scorer. Two paths:

  fast (vectorized)  when only board deals, betting and the showdown remain: sample the
                     opponent's hidden cards and the rest of every board from the unseen
                     cards in NumPy batches and score them with Scorer.shares_batch
  slow (rollouts)    anything else (card steps still to come, ...): Python rollouts of
                     the real rules on determinized worlds (see rollout.py)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from bot.equity import sample_without_replacement
from bot.sim.replay import Reconstruction

SIMPLE_STEPS = frozenset({"betting", "deal_board", "showdown"})


@dataclass
class ShareResult:
    share: float
    samples: int
    stderr: float
    path: str            # "fast" | "rollout"


def remaining_program(rec: Reconstruction):
    st = rec.state
    return st.rules.program[st.pc:]


def fast_path_ok(rec: Reconstruction) -> bool:
    """Only deals, betting and a plain showdown left (and a scorer with shares_batch)."""
    rest = remaining_program(rec)
    if any(s.type_name not in SIMPLE_STEPS for s in rest):
        return False
    if any(getattr(s, "runs", 1) > 1 for s in rest if s.type_name == "showdown"):
        pass                     # running it twice doesn't change the expected share
    return hasattr(rec.state.rules.evaluator, "shares_batch")


def fast_share(rec: Reconstruction, rng: np.random.Generator, time_budget_s: float,
               max_samples: int = 20000, first_chunk: int = 128, inference=None) -> ShareResult:
    """Vectorized expected share for the player `rec.me` (importance-weighted by
    `inference` when it is enabled and informative)."""
    st, me = rec.state, rec.me
    opp = 1 - me
    m = rec.mapping
    real = lambda toks: [m[t] if t < 0 else t for t in toks]  # noqa: E731
    my_hole = np.array(real(st.hole[me]), dtype=np.intp)
    known_opp = [m[t] for t in st.hole[opp] if t in m]
    unknown_opp = [t for t in st.hole[opp] if t not in m]
    n_opp_unknown = len(unknown_opp)
    rest = remaining_program(rec)
    n_boards = max(1, len(st.boards))
    to_deal = sum(s.n for s in rest if s.type_name == "deal_board")
    boards_now = ([real(st.board + b) for b in st.boards] if st.boards else [real(st.board)])
    pool = np.array(rec.pool, dtype=np.intp)
    need = n_opp_unknown + to_deal * n_boards
    if need > len(pool):
        raise ValueError("not enough unseen cards")
    scorer = st.rules.evaluator
    t0 = time.perf_counter()
    vals: list = []
    logws: list = []
    n = 0
    chunk = first_chunk
    while n < max_samples:
        draw = sample_without_replacement(rng, pool, chunk, need)
        if inference is not None and inference.enabled:
            cols = {t: draw[:, i] for i, t in enumerate(unknown_opp)}
            lw = inference.log_weights(rec, cols, chunk, rng)
            logws.append(lw if lw is not None else np.zeros(chunk))
        opp_hole = draw[:, :n_opp_unknown]
        if known_opp:
            opp_hole = np.concatenate([np.broadcast_to(np.array(known_opp), (chunk, len(known_opp))),
                                       opp_hole], axis=1)
        boards = []
        for b in range(n_boards):
            lo = n_opp_unknown + b * to_deal
            add = draw[:, lo:lo + to_deal]
            base = np.broadcast_to(np.array(boards_now[b], dtype=np.intp), (chunk, len(boards_now[b])))
            boards.append(np.concatenate([base, add], axis=1) if to_deal else base)
        mine = np.broadcast_to(my_hole, (chunk, len(my_hole)))
        sh = scorer.shares_batch(mine, opp_hole, boards)
        vals.append(sh)
        n += chunk
        elapsed = time.perf_counter() - t0
        left = time_budget_s - elapsed
        if left <= 0:
            break
        rate = n / max(elapsed, 1e-9)
        chunk = int(min(4096, max_samples - n, rate * left * 0.8))
        if chunk < 16:
            break
    v = np.concatenate(vals)
    mean, se = weighted_mean(v, np.concatenate(logws) if logws else None,
                             inference.params["min_ess"] if inference is not None else 0.0)
    return ShareResult(mean, n, se, "fast")


def weighted_mean(values: np.ndarray, logw, min_ess: float) -> tuple[float, float]:
    """Mean and standard error, importance-weighted when logw is given and healthy."""
    if logw is not None and np.any(logw != 0):
        w = np.exp(logw - logw.max())
        ess = w.sum() ** 2 / max((w * w).sum(), 1e-300)
        if ess >= min_ess * len(values):
            mean = float((w * values).sum() / w.sum())
            var = float((w * (values - mean) ** 2).sum() / w.sum())
            return mean, (var / ess) ** 0.5
    mean = float(values.mean())
    return mean, float(values.std() / max(1, len(values)) ** 0.5)


def expected_share(rec: Reconstruction, rng: np.random.Generator, time_budget_s: float,
                   max_samples: int = 20000, worlds: Optional[int] = None,
                   inference=None) -> ShareResult:
    """Expected showdown share, choosing the fast path when possible."""
    if fast_path_ok(rec):
        try:
            return fast_share(rec, rng, time_budget_s, max_samples, inference=inference)
        except ValueError:
            pass                                      # e.g. a dead hand: use rollouts
    from bot.sim.rollout import rollout_share
    return rollout_share(rec, rng, time_budget_s, max_worlds=worlds or 2000,
                         inference=inference)
