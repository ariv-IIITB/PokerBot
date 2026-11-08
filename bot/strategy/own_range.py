"""Our own range for the river solver (Tier 4, sub-plan R): weights over OUR 2-card combos, given the
line we took (every bet / call / check / raise we made this hand) and our public discard.

    own_range_weights(rec, combos, rng) -> weights over `combos` (sums to 1)

How: the same likelihood model the bot uses on the opponent (bot/sim/inference.py: a bet or raise is more
likely with a strong hand, a check or fold with a weak one, a public discard is a softmax over how good
the cards KEPT are), run on our own recorded decisions (`Reconstruction.my_decisions`). A candidate combo X
(two cards) is scored as the hand we would have held when each decision was made: before the discard it
was X plus our discarded card, which is public (`rec.mapping` holds it), after the discard it was X.
Combos holding a card we have seen on the board or in a public discard get weight 0.

THIS IS AN APPROXIMATION, and the main risk of re-solving the river without a safety gadget:
  * the model is a fit of our real choices on hand strength (OWN_BET above), not the real Tier 3 policy,
    which randomises, bluffs by blockers and follows the opponent's stats;
  * hand strength is a percentile against random hands on the board, so draws and blockers don't count;
  * each decision is treated as independent given the hand.
The weights are flatter than the truth where Tier 3 mixes and sharper where it is value-heavy. The
sensitivity check (`lab/river_sensitivity.py`) measures how much the solver's EV depends on them.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

import numpy as np

from bot.sim.inference import DEFAULTS as INFERENCE_DEFAULTS
from bot.sim.inference import Inference

# Our betting model, FITTED on our own Tier 3 river hands (lab/rd_trace.py, lab/rd_fit_own.py; 16,390 hands over 5
# training bots (the blind d_new_rules excluded), seeds 70000-70007, cross-fit by opponent): P(kind | board size, facing) = softmax of a_k + b_k * s,
# s = the strength percentile of the hand at that moment (Inference.strength). The generic BET_MODEL (gamma 3) scored
# our real hand BELOW a flat range (mean log(N*w) -1.8 vs 0); this model beats it in every cell out of sample
# (e.g. flop facing a bet: log-lik per decision -0.23 vs -0.85).
OWN_BET = {(0, False): {'K': (4.89, -6.87), 'R': (-4.89, 6.87)},
           (0, True): {'F': (-3.37, -1.95), 'C': (3.59, -1.58), 'R': (-0.22, 3.52)},
           (3, False): {'K': (1.33, -0.94), 'R': (-1.33, 0.94)},
           (3, True): {'F': (-2.99, -1.28), 'C': (2.7, 0.95), 'R': (0.29, 0.33)},
           (4, False): {'K': (2.02, -1.79), 'R': (-2.02, 1.79)},
           (4, True): {'F': (-2.36, -1.81), 'C': (6.05, -3.64), 'R': (-3.7, 5.45)},
           (5, False): {'K': (2.05, -1.11), 'R': (-2.05, 1.11)},
           (5, True): {'F': (-0.92, -0.54), 'C': (-0.92, -0.54), 'R': (1.84, 1.09)}}
OWN_BETA = 8.0            # discard softmax sharpness for our own discards (fitted: 6 -> -0.752, 9 -> -0.741)


class OwnInference(Inference):
    """Inference with the fitted OWN_BET table in place of the generic bet model (our decisions only)."""

    def _bet_ll(self, rec, d, holes, board, rng) -> np.ndarray:
        tab = OWN_BET.get((len(board), "C" in d.legal_kinds or "F" in d.legal_kinds))
        kinds = [k for k in d.legal_kinds if tab and k in tab]
        if d.action.kind not in kinds or len(kinds) < 2:
            return np.zeros(holes.shape[0])
        s = self.strength(rec, holes, board, rng)
        L = np.stack([tab[k][0] + tab[k][1] * s for k in kinds], axis=1)
        L = L - L.max(axis=1, keepdims=True)
        return (L - np.log(np.exp(L).sum(axis=1, keepdims=True)))[:, kinds.index(d.action.kind)]


def own_range_weights(rec, combos: np.ndarray, rng, inference: Optional[Inference] = None) -> np.ndarray:
    """Probability of each of our candidate 2-card hands given our line (sums to 1).

    rec        the Reconstruction at our current decision (needs `my_decisions`, `mapping`, `state`)
    combos     (n, k) real cards for our k still-held hole tokens, in hole order (k = 2 on the river)
    inference  the likelihood model (default: OwnInference, the fitted table above)
    If nothing in our line is informative the weights are uniform over the combos that are possible.
    """
    combos = np.asarray(combos, dtype=np.intp)
    n = len(combos)
    final = [t for t in rec.state.hole[rec.me]]
    if n == 0 or combos.shape[1] != len(final):
        raise ValueError(f"combos need {len(final)} cards per row")
    mapping = {t: c for t, c in rec.mapping.items() if t not in final}   # board + public discards
    shim = SimpleNamespace(state=rec.state, mapping=mapping, opp_decisions=list(rec.my_decisions),
                           me=rec.me)
    inf = inference or OwnInference(dict(INFERENCE_DEFAULTS, enabled=True, beta=OWN_BETA))
    logw = inf.log_weights(shim, {t: combos[:, i] for i, t in enumerate(final)}, n, rng)
    w = np.ones(n) if logw is None else np.exp(logw - logw.max())
    seen = np.array(sorted(set(mapping.values())), dtype=np.intp)
    if len(seen):
        w[np.isin(combos, seen).any(axis=1)] = 0.0
    total = w.sum()
    return w / total if total > 0 else w
