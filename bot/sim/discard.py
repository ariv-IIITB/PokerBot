"""The discard decision, vectorized: which hole card to throw away after the flop.

Keeping two of three cards is a small problem we can sample exactly instead of rolling out
whole hands. For each candidate (the card we drop) we deal, in NumPy batches, the opponent's
three hidden cards plus the turn and river from the unseen cards, let the opponent keep the
pair its own rule would keep, and score both showdowns. Every candidate is scored on the
SAME samples (common random numbers). If an `Inference` object is given, samples are
importance-weighted by how well the opponent's betting so far fits the dealt hand, so a
raiser's range counts as strong.

The opponent's rule, `opponent_keeps`, is the one every simple bot uses: keep the pair that
makes the best five-card hand with the flop, ties to the higher cards. It is also the rule
the rollouts use for any discard (bot/sim/rollout.py), so both sides of a rollout discard
sensibly instead of at random.

Only the standard one-card discard to the muck is handled here (what Discard Hold'em plays);
anything else returns None and the caller falls back to PIMC.
"""
from __future__ import annotations

import time
from itertools import combinations
from typing import Optional

import numpy as np

from bot.actions import Action, LegalActions
from bot.equity import sample_without_replacement
from bot.evaluator import CATEGORY_SHIFT, PAIR, STRAIGHT, TWO_PAIR, category
from bot.sim.replay import Reconstruction

RANK_WEIGHT = 128            # tie-break scale: hand value * 128 + sum of kept ranks (<= 24)


def keep_score(evaluator, kept, board) -> int:
    """Strength of keeping `kept` on `board` for the discard rule: the five-card hand value,
    then the kept cards' ranks (a deterministic tie-break), then a flush-draw nudge."""
    v = int(evaluator.evaluate(list(kept), list(board)))
    score = v * RANK_WEIGHT + sum(c >> 2 for c in kept)
    if category(v) < STRAIGHT and _suited_draw(kept, board):
        score += RANK_WEIGHT // 2                  # worth more than any tie-break, less than a pair
    return score


def _suited_draw(kept, board) -> bool:
    for s in range(4):
        if sum(1 for c in kept if c & 3 == s) == 2 and sum(1 for c in board if c & 3 == s) >= 2:
            return True
    return False


def opponent_keeps(evaluator, hole3: np.ndarray, board: np.ndarray) -> np.ndarray:
    """For (B, 3) hole cards: the (B, 2) cards the usual rule keeps (best hand with the flop)."""
    b = hole3.shape[0]
    best = np.full(b, -1, dtype=np.int64)
    kept = np.zeros((b, 2), dtype=np.intp)
    for pair in combinations(range(3), 2):
        cards = hole3[:, list(pair)]
        v = evaluator.evaluate_batch(cards, board).astype(np.int64) * RANK_WEIGHT \
            + (cards >> 2).sum(axis=1)
        better = v > best
        best = np.where(better, v, best)
        kept = np.where(better[:, None], cards, kept)
    return kept


def _opp_drop(evaluator, hole3: np.ndarray, board: np.ndarray) -> np.ndarray:
    """(B,) index (0..2) of the card `opponent_keeps` drops; same pair order and ties."""
    best = np.full(hole3.shape[0], -1, dtype=np.int64)
    drop = np.zeros(hole3.shape[0], dtype=np.intp)
    for pair, d in (((0, 1), 2), ((0, 2), 1), ((1, 2), 0)):
        cards = hole3[:, list(pair)]
        v = evaluator.evaluate_batch(cards, board).astype(np.int64) * RANK_WEIGHT \
            + (cards >> 2).sum(axis=1)
        better = v > best
        best = np.where(better, v, best)
        drop = np.where(better, d, drop)
    return drop


def straight_draw_batch(kept: np.ndarray, flop: np.ndarray) -> np.ndarray:
    """(B,) True when both kept (B,2) cards sit in a 5-rank window holding at least four distinct
    ranks of kept + flop (open-ended, gutshot or made); the ace counts high and low.
    Same rule as lab/opps/discard_rules._straight_draw."""
    b = kept.shape[0]
    kr, fr = kept >> 2, np.asarray(flop) >> 2
    rows = np.arange(b)
    out = np.zeros(b, dtype=bool)
    for ace_low in (False, True):
        ki = np.where(ace_low & (kr == 12), 0, kr + 1)           # slot 0 = ace low, slots 1..13 = ranks
        fi = np.where(ace_low & (fr == 12), 0, fr + 1)
        present = np.zeros((b, 14), dtype=bool)
        present[rows[:, None], ki] = True
        present[:, fi] = True
        for lo in range(10):
            inside = ((ki >= lo) & (ki <= lo + 4)).all(axis=1)
            out |= inside & (present[:, lo:lo + 5].sum(axis=1) >= 4)
    return out


def _draw_keeps(hole3: np.ndarray, board: np.ndarray) -> np.ndarray:
    """(B,3) bool: the drops the draw rule accepts (keep a straight draw, else drop the lowest)."""
    rank = hole3 >> 2
    score = np.empty(hole3.shape, dtype=np.int64)
    for i in range(3):
        score[:, i] = 16 * straight_draw_batch(hole3[:, [k for k in range(3) if k != i]], board) - rank[:, i]
    return score == score.max(axis=1, keepdims=True)


def opp_drop_probs(evaluator, hole3: np.ndarray, board: np.ndarray, w: float, eps: float) -> np.ndarray:
    """(B,3) P(opponent drops card i): with probability 1-w the `opponent_keeps` rule, with w the
    straight-draw rule (DB: together they explain 83-94 % of the training bots' discards), and
    probability eps a uniformly random card."""
    ok = np.eye(3)[_opp_drop(evaluator, hole3, board)]
    dk = _draw_keeps(hole3, board).astype(float)
    return (1 - eps) * ((1 - w) * ok + w * dk / dk.sum(axis=1, keepdims=True)) + eps / 3


def mixed_keeps(evaluator, hole3: np.ndarray, board: np.ndarray, w: float,
                rng: np.random.Generator) -> np.ndarray:
    """Like `opponent_keeps`, but each sampled opponent follows the straight-draw rule with probability w."""
    drop = np.where(rng.random(hole3.shape[0]) < w, _draw_keeps(hole3, board).argmax(axis=1),
                    _opp_drop(evaluator, hole3, board))
    cols = np.stack([np.where(drop == 0, 1, 0), np.where(drop == 2, 1, 2)], axis=1)
    return np.take_along_axis(hole3, cols, axis=1)


RULES = ("opponent_keeps", "drop_lowest", "keep_pair", "keep_straight_draw", "keep_flush_draw", "random")


def rule_masks(evaluator, hole3: np.ndarray, board: np.ndarray) -> np.ndarray:
    """(R, B, 3) bool: the drops each rule in RULES accepts (ties give several). Same rules as
    lab/opps/discard_rules (DB's fit); `board` is the 3-card flop."""
    b = hole3.shape[0]
    rank = hole3 >> 2
    out = np.zeros((len(RULES), b, 3), dtype=bool)
    out[0, np.arange(b), _opp_drop(evaluator, hole3, board)] = True
    out[1] = rank == rank.min(axis=1, keepdims=True)
    pair = np.empty((b, 3), dtype=bool)
    flush = np.empty((b, 3), dtype=bool)
    for i in range(3):
        kept = hole3[:, [k for k in range(3) if k != i]]
        pair[:, i] = (evaluator.evaluate_batch(kept, board).astype(np.int64) >> CATEGORY_SHIFT) >= PAIR
        suit = kept[:, 0] & 3
        flush[:, i] = (kept[:, 1] & 3 == suit) & ((np.asarray(board)[None, :] & 3 == suit[:, None]).sum(axis=1) >= 2)
    for r, flag in ((2, pair), (4, flush)):
        sc = 16 * flag - rank
        out[r] = sc == sc.max(axis=1, keepdims=True)
    out[3] = _draw_keeps(hole3, board)
    out[5] = True
    return out


class DiscardRules:
    """Online posterior over which rule in RULES the opponent discards by, from the discards we
    see at showdown (their three cards are then known). Each rule predicts a uniform pick among the
    drops it accepts, with probability `eps` of a random card instead; the prior favours the
    usual rule, so the posterior only moves when the evidence does."""

    def __init__(self, prior_usual: float = 0.5, eps: float = 0.1) -> None:
        self.eps = eps
        self.logprior = np.log(np.array([prior_usual] + [(1 - prior_usual) / (len(RULES) - 1)] * (len(RULES) - 1)))
        self.ll = np.zeros(len(RULES))
        self.n = 0

    def update(self, evaluator, hole3, flop, drop: int) -> None:
        m = rule_masks(evaluator, np.array([hole3], dtype=np.intp), np.array(flop, dtype=np.intp))[:, 0, :]
        p = (1 - self.eps) * m[:, drop] / m.sum(axis=1) + self.eps / 3
        self.ll += np.log(p)
        self.n += 1

    def posterior(self) -> np.ndarray:
        lp = self.logprior + self.ll
        w = np.exp(lp - lp.max())
        return w / w.sum()


def drop_dist(evaluator, hole3: np.ndarray, board: np.ndarray, post: np.ndarray, eps: float) -> np.ndarray:
    """(B,3) P(opponent drops card i) under the rule posterior."""
    m = rule_masks(evaluator, hole3, board).astype(float)
    p = np.einsum("r,rbi->bi", post, m / m.sum(axis=2, keepdims=True))
    return (1 - eps) * p + eps / 3


def learned_keeps(evaluator, hole3: np.ndarray, board: np.ndarray, post: np.ndarray,
                  rng: np.random.Generator) -> np.ndarray:
    """(B,2) kept cards when each sampled opponent follows a rule drawn from `post`."""
    b = hole3.shape[0]
    m = rule_masks(evaluator, hole3, board)[rng.choice(len(RULES), size=b, p=post), np.arange(b)]
    drop = np.argmax(m * rng.random((b, 3)), axis=1)      # random among the accepted drops
    cols = np.stack([np.where(drop == 0, 1, 0), np.where(drop == 2, 1, 2)], axis=1)
    return np.take_along_axis(hole3, cols, axis=1)


def _simple_discard(rec: Reconstruction) -> bool:
    step = rec.state.rules.program[rec.state.pc]
    return (step.type_name == "discard" and getattr(step, "n", 0) == 1
            and getattr(step, "destination", "") == "muck")


def choose_discard(rec: Reconstruction, legal: LegalActions, rng: np.random.Generator,
                   budget_s: float, inference=None, max_samples: int = 4000,
                   first_chunk: int = 96, out: Optional[dict] = None) -> Optional[Action]:
    """The best card to drop by sampled showdown share, or None when this is not the simple
    one-card discard (the caller then uses its generic policy). If `out` is a dict it receives
    "means": the sampled expected share of every option (only when the choice was sampled)."""
    if not _simple_discard(rec):
        return None
    st, me = rec.state, rec.me
    opp, m = 1 - me, rec.mapping
    mine = [m.get(t, t) for t in st.hole[me]]
    if len(mine) != 3 or any(c < 0 for c in mine):
        return None
    if len(st.hole[opp]) != 3 or any(t in m for t in st.hole[opp]):
        return None
    board = [m.get(t, t) for t in st.board]
    if len(board) != 3 or any(c < 0 for c in board):
        return None
    options = {o: int(o) for o in legal.special.choices if o.isdigit()}
    if len(options) != 3:
        return None
    scorer = st.rules.evaluator
    to_deal = sum(s.n for s in st.rules.program[st.pc:] if s.type_name == "deal_board")
    pool = np.array(rec.pool, dtype=np.intp)
    need = 3 + to_deal
    if need > len(pool):
        return None
    cands = {o: [c for k, c in enumerate(mine) if k != i] for o, i in options.items()}

    # Obvious cases need no sampling: one keep makes at least a straight and beats the others.
    cats = {o: category(int(scorer.evaluate(cards, board))) for o, cards in cands.items()}
    top = max(cats.values())
    if top >= STRAIGHT and sum(1 for v in cats.values() if v == top) == 1:
        return Action.special(next(o for o, v in cats.items() if v == top))

    board_np = np.array(board, dtype=np.intp)
    mix = float(inference.params.get("discard_mix", 0.0)) if inference is not None else 0.0
    learned = None
    stake = 0.0
    if inference is not None:
        if not getattr(scorer, "hilo", False) and getattr(scorer, "low", None) is None:
            stake = float(inference.params.get("discard_stake", 0.0))
        max_samples = int(inference.params.get("discard_max_samples", max_samples))
        if inference.params.get("discard_learn") and inference.rules.n > 0:
            learned = inference.rules.posterior()
    t0 = time.perf_counter()
    totals = {o: [] for o in cands}
    logws: list[np.ndarray] = []
    n, chunk = 0, first_chunk
    while n < max_samples:
        draw = sample_without_replacement(rng, pool, chunk, need)
        if inference is not None and inference.enabled:
            cols = {t: draw[:, i] for i, t in enumerate(st.hole[opp])}
            lw = inference.log_weights(rec, cols, chunk, rng)
            logws.append(lw if lw is not None else np.zeros(chunk))
        if learned is not None:
            opp_kept = learned_keeps(scorer, draw[:, :3], board_np, learned, rng)
        elif mix > 0:
            opp_kept = mixed_keeps(scorer, draw[:, :3], board_np, mix, rng)
        else:
            opp_kept = opponent_keeps(scorer, draw[:, :3], board_np)
        full = np.concatenate([np.broadcast_to(board_np, (chunk, 3)), draw[:, 3:3 + to_deal]], axis=1)
        v1 = scorer.primary.evaluate_batch(opp_kept, full) if stake > 0 else None
        for o, cards in cands.items():
            mine_b = np.broadcast_to(np.array(cards, dtype=np.intp), (chunk, 2))
            if stake > 0:
                v0 = scorer.primary.evaluate_batch(mine_b, full)
                share = (v0 > v1) + 0.5 * (v0 == v1)
                big = (np.maximum(v0, v1) >> CATEGORY_SHIFT) >= TWO_PAIR
                totals[o].append(0.5 + (share - 0.5) * (1.0 + stake * big))   # pot grows when someone holds two pair or better
            else:
                totals[o].append(scorer.shares_batch(mine_b, opp_kept, [full]))
        n += chunk
        left = budget_s - (time.perf_counter() - t0)
        if left <= 0:
            break
        rate = n / max(time.perf_counter() - t0, 1e-9)
        chunk = int(min(2048, max_samples - n, rate * left * 0.8))
        if chunk < 16:
            break
    values = {o: np.concatenate(v) for o, v in totals.items()}
    w = None
    if logws:
        lw = np.concatenate(logws)
        if np.any(lw != 0):
            cand = np.exp(lw - lw.max())
            ess = cand.sum() ** 2 / max((cand * cand).sum(), 1e-300)
            if ess >= inference.params["min_ess"] * len(lw):
                w = cand
    means = {o: float(np.average(v, weights=w)) for o, v in values.items()}
    if out is not None:
        out["means"] = means
    best = max(means, key=lambda o: (means[o], -int(o)))
    return Action.special(best)
