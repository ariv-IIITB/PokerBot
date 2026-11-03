"""Type posterior on the opponent (build map X2; book sections 1.4.3 and 2.9).

A small library of styles (over-folder, value-only, station, trapper, aggressor, unknown), each with
P(action | street, facing our bet) and the slow traits a match is too short to measure (how many of
its shown river bets are bluffs). Naive Bayes over the opponent's decisions gives a posterior over
the styles; `implied("river_bluff")` turns a fast observation into a belief about the slow trait.
"unknown" is a flattened population average. A fit check catches styles outside the library: when
even the best type is far from the observed actions (KL per decision, minus its sampling bias),
the posterior moves to "unknown" (a random bot is not confidently matched to a real one).

The library is the embedded artifact "types" (data/<variant>/types.json, built by lab/opps/types.py).
Fed from the same message stream as the trait tests (`update(state, msg)`); nothing decides on it yet.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from bot.protocol import Message, OppAction
from bot.state import GameState
from bot.strategy.traits import Event, classify

ACTS = ("F", "P", "R")             # fold, passive (check or call), raise
N_CTX = 8                          # street (4) x facing our bet (2)
TEMPERATURE = 0.5                  # scales the log-likelihood: naive Bayes is over-confident
MISFIT_LO, MISFIT_HI = 0.03, 0.06  # bias-corrected KL to the best type: from LO, mass moves to
                                   # "unknown", all of it at HI (known bots stay below 0.02)


def context_index(ev: Event) -> tuple[int, int]:
    """(context, action) indices of one opponent decision."""
    act = 0 if ev.kind == "F" else (2 if ev.kind == "R" else 1)
    return 2 * ev.street + int(ev.facing), act


class TypePosterior:
    def __init__(self, library: dict, temperature: float = TEMPERATURE) -> None:
        self.names = list(library["types"])
        self.logp = np.log(np.array([library["types"][n]["probs"] for n in self.names], dtype=float))
        self.slow = [library["types"][n]["slow"] for n in self.names]
        self.family = {n: library["types"][n].get("family", n) for n in self.names}
        self.unknown = self.names.index("unknown") if "unknown" in self.names else None
        self.counts = np.zeros((N_CTX, len(ACTS)))
        self.temperature = temperature
        self.score = np.zeros(len(self.names))       # uniform prior
        self.n = 0

    @classmethod
    def from_rules(cls, rules) -> Optional["TypePosterior"]:
        """From the embedded artifact built for this variant, else None."""
        from bot.artifacts import embedded
        art = embedded("types", rules)
        return cls(art["meta"]) if art is not None else None

    def update(self, state: GameState, msg: Message) -> None:
        h = state.hand
        if isinstance(msg, OppAction) and h is not None:
            ev = classify(h.history)
            if ev is not None:
                self.observe(ev)

    def observe(self, ev: Event) -> None:
        ctx, act = context_index(ev)
        self.score += self.temperature * self.logp[:, ctx, act]
        self.counts[ctx, act] += 1
        self.n += 1

    def misfit(self) -> float:
        """KL (per decision) from the observed actions to the closest library type, minus its
        expected sampling bias (df / 2N). About 0 for a bot in the library."""
        if self.n == 0:
            return 0.0
        c = self.counts
        n_ctx = c.sum(axis=1, keepdims=True)
        emp = c / np.maximum(n_ctx, 1)
        mask = c > 0
        best = math.inf
        for k in range(len(self.names)):
            if k == self.unknown:
                continue
            kl = float((c[mask] * (np.log(emp[mask]) - self.logp[k][mask])).sum()) / self.n
            best = min(best, kl)
        return best - 2 * int((n_ctx > 0).sum()) / (2 * self.n)

    def posterior(self) -> dict[str, float]:
        z = self.score - self.score.max()
        p = np.exp(z)
        p /= p.sum()
        if self.unknown is not None:
            u = min(1.0, max(0.0, (self.misfit() - MISFIT_LO) / (MISFIT_HI - MISFIT_LO)))
            if u > 0:
                p = (1 - u) * p
                p[self.unknown] += u
        return {n: float(x) for n, x in zip(self.names, p)}

    def families(self) -> dict[str, float]:
        """The posterior summed by style family (over-folder, aggressor, ...)."""
        out: dict[str, float] = {}
        for n, x in self.posterior().items():
            out[self.family[n]] = out.get(self.family[n], 0.0) + x
        return out

    def top(self) -> tuple[str, float]:
        post = self.posterior()
        name = max(post, key=post.get)
        return name, post[name]

    def implied(self, trait: str) -> float:
        """Posterior-weighted slow trait, e.g. "river_bluff" (share of river bets that are bluffs)."""
        post = self.posterior()
        return math.fsum(post[n] * float(s.get(trait, 0.0)) for n, s in zip(self.names, self.slow))
