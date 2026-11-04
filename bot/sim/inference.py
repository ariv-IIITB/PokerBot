"""Inference from public information: weight sampled opponent hands by how likely the
opponent's visible choices were.

Opponent model ("self-model", simplified for speed): the opponent plays sensibly, like
our generic policy would.
  public discard   P(discard option o | hand) is a softmax over how good the cards they
                   KEEP are: a hand that would rarely throw an ace away becomes less likely
                   after an ace hits the board from their hand
  bet / raise      more likely with stronger hands; checks and folds with weaker ones:
                   logits = gamma x (strength - pivot) per action kind
Hand strength = percentile of the hand against random hands on that board (a quick
"hand strength now"), or a rank-based proxy when there aren't enough cards to score.
Weights are importance weights over the samples; if they collapse (effective sample size
below `min_ess` of the samples) the estimate falls back to unweighted.

Trust calibration: the model is only right for sensible opponents (a maniac raises with
anything). After every showdown, `Trust.update` scores the opponent's revealed hand: the
log-likelihood of their decisions under the model minus under random play (per decision,
separately for bets and discards). The running averages give trust levels in [0, 1]
that scale gamma and beta, so inference fades out against opponents it doesn't describe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from bot.actions import CALL, CHECK, FOLD, RAISE

DEFAULTS = {
    "enabled": False,
    "beta": 6.0,          # discard softmax sharpness (per unit of strength)
    "gamma": 3.0,         # betting sharpness
    "ref_hands": 120,     # random hands used to turn hand values into percentiles
    "min_ess": 0.08,      # fall back to unweighted below this fraction
    "discard_mix": 0.0,   # >0: discard likelihood = 2-rule mixture (bot/sim/discard.opp_drop_probs), this weight on the draw rule
    "discard_eps": 0.25,  # ... plus this share of random discards
}

# logit = gamma * slope * (strength - pivot)
BET_MODEL = {RAISE: (2.0, 0.55), CALL: (1.0, 0.35), CHECK: (-0.5, 0.5), FOLD: (-2.0, 0.25)}


@dataclass
class OppDecision:
    kind: str                         # "discard" | "bet"
    action: object
    hole: tuple                       # opponent hole tokens when deciding
    board: tuple                      # board tokens then
    options: tuple = ()               # discard options (choice strings)
    legal_kinds: tuple = ()           # betting: legal action kinds then


@dataclass
class Inference:
    params: dict = field(default_factory=lambda: dict(DEFAULTS))

    @property
    def enabled(self) -> bool:
        return bool(self.params.get("enabled"))

    # ---- strength
    def strength(self, rec, holes: np.ndarray, board: list[int], rng) -> np.ndarray:
        """Hand strength in [0, 1] for each row of `holes` on `board`."""
        ev = rec.state.rules.evaluator
        if len(board) >= 3:
            try:
                vals = ev.evaluate_batch(holes, board)
                dead = set(board) | set(np.unique(holes).tolist())
                pool = np.array([c for c in rec.state.rules.deck if c not in dead])
                k = holes.shape[1]
                if len(pool) >= k:
                    n = int(self.params["ref_hands"])
                    idx = np.argsort(rng.random((n, len(pool))), axis=1)[:, :k]
                    ref = np.sort(ev.evaluate_batch(pool[idx], board))
                    return np.searchsorted(ref, vals, side="right") / len(ref)
            except ValueError:
                pass
        faces = holes % 64
        ranks = np.where(faces < 52, faces // 4, 6)
        top = np.sort(ranks, axis=1)[:, ::-1]
        s = top[:, 0] / 12.0 * 0.55 + (top[:, 1] / 12.0 * 0.25 if top.shape[1] > 1 else 0)
        if top.shape[1] > 1:
            paired = (np.diff(np.sort(ranks, axis=1), axis=1) == 0).any(axis=1)
            s = s + 0.25 * paired
        return np.clip(s, 0.0, 1.0)

    # ---- likelihood
    def log_weights(self, rec, columns: dict, n: int, rng) -> Optional[np.ndarray]:
        """Log importance weights for n samples. columns: token -> (n,) array of the card
        each sample assigns to that hidden token. None if nothing informative."""
        if not self.enabled:
            return None
        logw = np.zeros(n)
        used = False
        m = rec.mapping
        for d in getattr(rec, "opp_decisions", ()):
            cols = []
            ok = True
            for t in d.hole:
                if t in m:
                    cols.append(np.full(n, m[t]))
                elif t in columns:
                    cols.append(columns[t])
                else:
                    ok = False
                    break
            board = [m.get(t) for t in d.board]
            if not ok or any(c is None for c in board) or not cols:
                continue
            holes = np.stack(cols, axis=1).astype(np.intp)
            if d.kind == "discard":
                logw += self._discard_ll(rec, d, holes, board, rng)
                used = True
            elif d.kind == "bet":
                logw += self._bet_ll(rec, d, holes, board, rng)
                used = True
        return logw if used else None

    def _discard_ll(self, rec, d, holes, board, rng) -> np.ndarray:
        beta = float(self.params["beta"])
        opts = [o for o in d.options if o != "none"]
        h = holes.shape[1]
        mix = float(self.params.get("discard_mix", 0.0))
        if mix > 0 and h == 3 and len(board) == 3 and sorted(opts) == ["0", "1", "2"] \
                and d.action.choice in opts:
            from bot.sim.discard import opp_drop_probs
            p = opp_drop_probs(rec.state.rules.evaluator, holes, np.array(board, dtype=np.intp), mix,
                               float(self.params.get("discard_eps", 0.25)))
            # trust scales beta; tempering the mixture by beta / full beta gives uniform at 0
            L = np.log(p) * (beta / DEFAULTS["beta"])
            L = L - L.max(axis=1, keepdims=True)
            logp = L - np.log(np.exp(L).sum(axis=1, keepdims=True))
            return logp[:, int(d.action.choice)]
        logits = []
        for o in opts:
            drop = [int(x) for x in o.split("+")]
            keep = [i for i in range(h) if i not in drop]
            if not keep:
                logits.append(np.zeros(holes.shape[0]))
                continue
            logits.append(beta * self.strength(rec, holes[:, keep], board, rng))
        L = np.stack(logits, axis=1)
        L = L - L.max(axis=1, keepdims=True)
        logp = L - np.log(np.exp(L).sum(axis=1, keepdims=True))
        chosen = opts.index(d.action.choice) if d.action.choice in opts else None
        return logp[:, chosen] if chosen is not None else np.zeros(holes.shape[0])

    def _bet_ll(self, rec, d, holes, board, rng) -> np.ndarray:
        gamma = float(self.params["gamma"])
        s = self.strength(rec, holes, board, rng)
        kinds = [k for k in d.legal_kinds if k in BET_MODEL]
        if d.action.kind not in kinds or len(kinds) < 2:
            return np.zeros(holes.shape[0])
        L = np.stack([gamma * BET_MODEL[k][0] * (s - BET_MODEL[k][1]) for k in kinds], axis=1)
        L = L - L.max(axis=1, keepdims=True)
        logp = L - np.log(np.exp(L).sum(axis=1, keepdims=True))
        return logp[:, kinds.index(d.action.kind)]

    def decision_llr(self, rec, opp_cards, rng) -> dict:
        """Per-kind (sum of log-likelihood ratio model vs random, decisions scored) for the
        opponent's decisions in `rec`, given their revealed hole cards `opp_cards`."""
        opp = 1 - rec.me
        toks = list(rec.state.hole[opp])
        if len(toks) != len(opp_cards):
            return {}
        cols = {t: np.array([c]) for t, c in zip(toks, opp_cards) if t not in rec.mapping}
        out = {}
        for kind in ("bet", "discard"):
            ds = [d for d in getattr(rec, "opp_decisions", ()) if d.kind == kind]
            if not ds:
                continue
            sub = type(rec)(rec.state, rec.me, rec.mapping, rec.unknown, rec.pool,
                            opp_decisions=ds)
            full = Inference(dict(self.params, enabled=True))
            flat = Inference(dict(self.params, enabled=True, beta=0.0, gamma=0.0))
            a = full.log_weights(sub, cols, 1, rng)
            b = flat.log_weights(sub, cols, 1, rng)
            if a is not None and b is not None:
                out[kind] = (float(a[0] - b[0]), len(ds))
        return out

    def weights(self, rec, columns: dict, n: int, rng) -> Optional[np.ndarray]:
        """Normalized weights (mean 1), or None (no information / weights collapsed)."""
        logw = self.log_weights(rec, columns, n, rng)
        if logw is None:
            return None
        w = np.exp(logw - logw.max())
        ess = w.sum() ** 2 / max((w * w).sum(), 1e-300)
        if ess < float(self.params["min_ess"]) * n:
            return None
        return w * (n / w.sum())


class Trust:
    """Running trust in the opponent model, per decision kind ("bet", "discard").
    trust = clip(mean LLR per decision / full_llr, 0, 1), with the mean shrunk toward
    `prior_llr` (trust 0.5 to start) with weight `k` pseudo-decisions. Measured: a sensible
    opponent scores about +0.2 per decision, a maniac or a random bot about 0 or below."""

    def __init__(self, full_llr: float = 0.15, k: float = 6.0, prior_llr: float = 0.075) -> None:
        self.full, self.k, self.prior = full_llr, k, prior_llr
        self.sum = {"bet": 0.0, "discard": 0.0}
        self.n = {"bet": 0, "discard": 0}

    def update(self, llrs: dict) -> None:
        for kind, (llr, n) in llrs.items():
            self.sum[kind] += llr
            self.n[kind] += n

    def level(self, kind: str) -> float:
        mean = (self.sum[kind] + self.prior * self.k) / (self.n[kind] + self.k)
        return float(min(1.0, max(0.0, mean / self.full)))
