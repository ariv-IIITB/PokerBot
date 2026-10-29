"""Equity-histogram buckets per street (for abstraction, e.g. MCCFR in phase 22).

For each street with a board, sample situations (our hole + that street's board), build
the histogram of our final equity over random runouts, and cluster the histograms with
K-means under EMD (in 1-D, EMD = L1 distance between CDFs, so we cluster CDF vectors with
L1 / k-medians-style updates). Saves per street: centroids (K x bins CDFs) and the
situations' assignments. Deterministic for a seed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from bot.abstraction import showdown_share
from bot.equity import sample_without_replacement

BINS = 10


def _hist_cdf(rules, hole, board, rng, runouts: int = 16, opps: int = 48) -> np.ndarray:
    """CDF of our final equity over `runouts` completions of the board."""
    deck = np.array([c for c in rules.deck if c not in set(hole) | set(board)])
    need = rules.board_cards - len(board)
    ev = rules.evaluator
    eqs = []
    for _ in range(runouts):
        run = sample_without_replacement(rng, deck, 1, need)[0] if need else np.zeros(0, int)
        full = np.concatenate([np.array(board, dtype=np.intp), run]).astype(np.intp)
        rest = np.array([c for c in deck if c not in set(run.tolist())])
        opp = sample_without_replacement(rng, rest, opps, len(hole))
        mine = np.broadcast_to(np.array(hole), (opps, len(hole)))
        eqs.append(float(showdown_share(ev, mine, opp, full).mean()))
    h, _ = np.histogram(eqs, bins=BINS, range=(0, 1))
    return np.cumsum(h) / max(1, h.sum())


def kmeans_emd(cdfs: np.ndarray, k: int, rng, iters: int = 25) -> tuple[np.ndarray, np.ndarray]:
    """K-means-style clustering of CDF vectors under L1 (EMD); medians minimize L1."""
    k = min(k, len(cdfs))
    cent = cdfs[rng.choice(len(cdfs), size=k, replace=False)]
    assign = np.zeros(len(cdfs), dtype=np.int32)
    for _ in range(iters):
        d = np.abs(cdfs[:, None, :] - cent[None, :, :]).sum(axis=2)
        new = d.argmin(axis=1).astype(np.int32)
        if np.array_equal(new, assign) and _ > 0:
            break
        assign = new
        for j in range(k):
            members = cdfs[assign == j]
            if len(members):
                cent[j] = np.median(members, axis=0)
    return cent, assign


def build_buckets(rules, out: Path, k: int, seed: int, samples: int = 2000) -> None:
    rng = np.random.default_rng(seed)
    hole_n = rules.hole_cards
    board_sizes = sorted({sum(rules.streets[: i + 1]) for i in range(1, len(rules.streets))})
    for street, b in enumerate(board_sizes, start=1):
        cdfs = []
        deck = np.array(rules.deck)
        for _ in range(samples):
            cards = sample_without_replacement(rng, deck, 1, hole_n + b)[0].tolist()
            cdfs.append(_hist_cdf(rules, cards[:hole_n], cards[hole_n:], rng))
        cdfs = np.array(cdfs)
        cent, assign = kmeans_emd(cdfs, k, rng)
        np.save(out / f"buckets_s{street}_centroids.npy", cent.astype(np.float32))
        np.save(out / f"buckets_s{street}_assign.npy", assign)
        print(f"buckets street {street}: {len(cent)} clusters from {samples} situations")
