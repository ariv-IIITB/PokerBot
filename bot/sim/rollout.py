"""Rollouts and Perfect-Information Monte Carlo (PIMC) on determinized worlds.

A world is one consistent guess of every hidden card (Reconstruction.world). A rollout
plays the real rules from the current position with a cheap policy:
  betting   check when free, otherwise call  ("check-down")
  specials  a random legal option (bids: 0; quotes: the middle of the range)

Speed trick ("roll to simple, then batch"): each world is played in Python only until
nothing but board deals, betting and the showdown remain. From there the check-down
result is just "deal the rest of the board(s) and score", so every world's remaining
board is re-dealt `runouts` times from its undealt cards and all of them are scored in
one vectorized batch. Variants with side payments that the batch doesn't model
(bounties, side markets) fall back to full Python rollouts.

PIMC compares candidate choices by mean value over the SAME worlds with the same rollout
randomness for every candidate (common random numbers). Everything stops on time.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np

from bot.actions import Action
from bot.equity import sample_without_replacement
from bot.game.runner import STOP, act, advance, legal_actions
from bot.sim.replay import Reconstruction

SIMPLE_STEPS = frozenset({"betting", "deal_board", "showdown"})


def rollout_policy(rng: np.random.Generator) -> Callable:
    def policy(st, p, legal):
        if legal.can_special:
            sp = legal.special
            if sp.is_range:
                return Action.special(str(sp.lo if sp.name == "bid" else (sp.lo + sp.hi) // 2))
            return Action.special(sp.choices[int(rng.integers(len(sp.choices)))])
        if legal.check:
            return Action.check()
        return Action.call() if legal.call else Action.fold()
    return policy


def is_simple_point(st) -> bool:
    return all(s.type_name in SIMPLE_STEPS for s in st.rules.program[st.pc:])


def needs_full_rollout(st) -> bool:
    """Side payments the batched scorer doesn't model."""
    return bool(st.extra.get("bounty") or st.extra.get("market")
                or getattr(st.rules, "payoffs", ()))


def play_to_end(st, policy, rng) -> None:
    while True:
        p = advance(st, rng)
        if p is None:
            return
        act(st, p, policy(st, p, legal_actions(st, p)))


def play_to_simple(st, policy, rng) -> bool:
    """Play until only simple steps remain (True) or the hand ends (False)."""
    while True:
        p = advance(st, rng, stop=is_simple_point)
        if p == STOP:
            return True
        if p is None:
            return False
        act(st, p, policy(st, p, legal_actions(st, p)))


# --------------------------------------------------------------------------- batching

@dataclass
class _Pending:
    """A world paused at a simple point, waiting for batched scoring."""
    key: object                  # who to credit (candidate index, world index)
    stack: float                 # our stack now
    pot: int
    mine: list
    opp: list
    boards: list                 # current board(s)
    deck: list                   # undealt cards
    to_deal: int
    n_boards: int


def _pending(st, me: int, key) -> _Pending:
    rest = st.rules.program[st.pc:]
    to_deal = sum(s.n for s in rest if s.type_name == "deal_board")
    boards = [st.board + b for b in st.boards] if st.boards else [list(st.board)]
    return _Pending(key, float(st.stack[me]), st.pot, list(st.hole[me]), list(st.hole[1 - me]),
                    boards, list(st.deck), to_deal, len(boards))


def score_pending(items: Sequence[_Pending], scorer, rng, runouts: int) -> list[float]:
    """Mean share for each paused world, `runouts` board completions each, batched by shape."""
    out = [0.0] * len(items)
    groups: dict = {}
    for i, it in enumerate(items):
        shape = (len(it.mine), len(it.opp), tuple(len(b) for b in it.boards), it.to_deal)
        groups.setdefault(shape, []).append(i)
    for shape, idx in groups.items():
        rows_mine, rows_opp, rows_boards = [], [], [[] for _ in range(len(shape[2]))]
        for i in idx:
            it = items[i]
            deck = np.asarray(it.deck, dtype=np.intp)
            need = it.to_deal * it.n_boards
            draw = (sample_without_replacement(rng, deck, runouts, need) if need
                    else np.zeros((runouts, 0), dtype=np.intp))
            rows_mine.append(np.broadcast_to(np.asarray(it.mine, dtype=np.intp), (runouts, len(it.mine))))
            rows_opp.append(np.broadcast_to(np.asarray(it.opp, dtype=np.intp), (runouts, len(it.opp))))
            for b in range(it.n_boards):
                base = np.broadcast_to(np.asarray(it.boards[b], dtype=np.intp),
                                       (runouts, len(it.boards[b])))
                add = draw[:, b * it.to_deal:(b + 1) * it.to_deal]
                rows_boards[b].append(np.concatenate([base, add], axis=1))
        mine = np.concatenate(rows_mine)
        opp = np.concatenate(rows_opp)
        boards = [np.concatenate(rb) for rb in rows_boards]
        try:
            sh = scorer.shares_batch(mine, opp, boards).reshape(len(idx), runouts).mean(axis=1)
        except ValueError:                  # a dead hand somewhere: score one by one
            sh = []
            for k, i in enumerate(idx):
                lo, hi = k * runouts, (k + 1) * runouts
                try:
                    sh.append(float(scorer.shares_batch(mine[lo:hi], opp[lo:hi],
                                                        [b[lo:hi] for b in boards]).mean()))
                except ValueError:
                    sh.append(0.5)
        for k, i in enumerate(idx):
            out[i] = float(sh[k])
    return out


# --------------------------------------------------------------------------- share

@dataclass
class RolloutShare:
    share: float
    samples: int
    stderr: float
    path: str = "rollout"


def _batch_worlds(rec, rng, batch, inference):
    """`batch` determinized worlds and their log importance weights."""
    cols = rec.assignments(rng, batch)
    lw = None
    if inference is not None and inference.enabled:
        lw = inference.log_weights(rec, cols, batch, rng)
    lw = lw if lw is not None else np.zeros(batch)
    return [rec.world_from(cols, i) for i in range(batch)], lw


def _next_batch(done: int, started: float, batch_started: float, size: int, budget_s: float,
                cap: int, remaining: int) -> int:
    """Worlds for the next batch: as many as fit in what is left of the budget at the rate just
    measured (a batch is the unit of overshoot, so it must shrink with the budget)."""
    now = time.perf_counter()
    per_world = max((now - batch_started) / max(1, size), 1e-6)
    left = budget_s - (now - started)
    return int(max(2, min(cap, remaining, left / per_world * 0.8)))


def rollout_share(rec: Reconstruction, rng: np.random.Generator, time_budget_s: float,
                  max_worlds: int = 2000, runouts: int = 16, batch: int = 48,
                  inference=None) -> RolloutShare:
    """Expected showdown share by check-down rollouts (works for any rules). Worlds are
    rolled and scored in batches that start small and are sized to fit the time left, so a
    tight budget is overshot by a couple of worlds, not by a fixed dozen."""
    from bot.sim.share import weighted_mean
    t0 = time.perf_counter()
    me = rec.me
    vals: list[float] = []
    logws: list[float] = []
    weights: list[int] = []
    n = 0
    scorer = rec.state.rules.evaluator
    size = min(batch, 4)
    while n < max_worlds and (n == 0 or time.perf_counter() - t0 < time_budget_s):
        pend: list[_Pending] = []
        b0 = time.perf_counter()
        ws, lw = _batch_worlds(rec, rng, size, inference)
        lw_pend = []
        for j, w in enumerate(ws):
            r = np.random.default_rng(int(rng.integers(2**62)))
            if needs_full_rollout(w) or not play_to_simple(w, rollout_policy(r), r):
                play_to_end(w, rollout_policy(r), r)
                shares = w.extra.get("shares")
                vals.append(shares[me] if shares is not None else float(w.folded == 1 - me))
                logws.append(float(lw[j]))
                weights.append(1)
            else:
                pend.append(_pending(w, me, n))
                lw_pend.append(float(lw[j]))
            n += 1
        if pend:
            vals += score_pending(pend, scorer, rng, runouts)
            logws += lw_pend
            weights += [runouts] * len(pend)
        size = _next_batch(n, t0, b0, size, time_budget_s, batch, max_worlds - n)
    min_ess = inference.params["min_ess"] if inference is not None else 0.0
    mean, se = weighted_mean(np.asarray(vals), np.asarray(logws), min_ess)
    return RolloutShare(mean, int(sum(weights)), se)


# --------------------------------------------------------------------------- PIMC

@dataclass
class PimcResult:
    best: Action
    values: dict = field(default_factory=dict)        # choice -> mean value
    worlds: int = 0
    rollouts: int = 0


def pimc(rec: Reconstruction, candidates: Sequence[Action], rng: np.random.Generator,
         time_budget_s: float, max_worlds: int = 400, runouts: int = 12, batch: int = 24,
         value_fn: Optional[Callable] = None, apply_fn: Optional[Callable] = None,
         inference=None) -> PimcResult:
    """Pick the candidate with the best mean value for us over shared worlds.

    value: our expected final stack (stack now + share x pot when batched).
    apply_fn(world, candidate) applies a candidate (default: act() it as our choice).
    value_fn(final_state, me) -> float forces full rollouts with a custom value.
    Worlds are processed `batch` at a time; the budget is checked between batches."""
    t0 = time.perf_counter()
    me = rec.me
    k = len(candidates)
    per_world: list[list[float]] = []      # value of each candidate in each world
    logw_all: list[float] = []
    worlds = rollouts = 0
    apply_fn = apply_fn or (lambda w, a: act(w, me, a))
    scorer = rec.state.rules.evaluator
    size = min(batch, 2)
    while worlds < max_worlds and (worlds == 0 or time.perf_counter() - t0 < time_budget_s):
        pend: list[_Pending] = []
        b0 = time.perf_counter()
        bases, lw = _batch_worlds(rec, rng, size, inference)
        for j, base in enumerate(bases):
            seed = int(rng.integers(2**62))
            row = [0.0] * k
            for i, a in enumerate(candidates):
                w = base.copy()
                r = np.random.default_rng(seed)        # same randomness for every candidate
                apply_fn(w, a)
                if (value_fn is None and not needs_full_rollout(w)
                        and play_to_simple(w, rollout_policy(r), r)):
                    pend.append(_pending(w, me, (len(per_world), i)))
                else:
                    play_to_end(w, rollout_policy(r), r)
                    row[i] = value_fn(w, me) if value_fn else float(w.stack[me])
                rollouts += 1
            per_world.append(row)
            logw_all.append(float(lw[j]))
            worlds += 1
        if pend:
            for it, sh in zip(pend, score_pending(pend, scorer, rng, runouts)):
                wi, ci = it.key
                per_world[wi][ci] = it.stack + sh * it.pot
        size = _next_batch(worlds, t0, b0, size, time_budget_s, batch, max_worlds - worlds)
    vals = np.asarray(per_world)
    logw = np.asarray(logw_all)
    w = np.ones(len(vals))
    if np.any(logw != 0):
        cand = np.exp(logw - logw.max())
        ess = cand.sum() ** 2 / max((cand * cand).sum(), 1e-300)
        min_ess = inference.params["min_ess"] if inference is not None else 0.0
        if ess >= min_ess * len(vals):
            w = cand
    means = list((w[:, None] * vals).sum(axis=0) / w.sum())
    values = {(candidates[i].choice if candidates[i].choice is not None else str(candidates[i])):
              means[i] for i in range(k)}
    best_i = max(range(k), key=lambda i: (means[i], -i))
    return PimcResult(candidates[best_i], values, worlds, rollouts)
