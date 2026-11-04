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
  * the model is a generic "sensible player" (default beta / gamma, not scaled by any trust), not
    the real Tier 3 policy, which randomises, bluffs by blockers and follows the opponent's stats;
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


def own_range_weights(rec, combos: np.ndarray, rng, inference: Optional[Inference] = None) -> np.ndarray:
    """Probability of each of our candidate 2-card hands given our line (sums to 1).

    rec        the Reconstruction at our current decision (needs `my_decisions`, `mapping`, `state`)
    combos     (n, k) real cards for our k still-held hole tokens, in hole order (k = 2 on the river)
    inference  the likelihood model (default: the standard parameters, enabled, no trust scaling)
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
    inf = inference or Inference(dict(INFERENCE_DEFAULTS, enabled=True))
    logw = inf.log_weights(shim, {t: combos[:, i] for i, t in enumerate(final)}, n, rng)
    w = np.ones(n) if logw is None else np.exp(logw - logw.max())
    seen = np.array(sorted(set(mapping.values())), dtype=np.intp)
    if len(seen):
        w[np.isin(combos, seen).any(axis=1)] = 0.0
    total = w.sum()
    return w / total if total > 0 else w
