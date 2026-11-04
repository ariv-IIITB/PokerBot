"""Opponent statistics with shrinkage toward priors.

Each stat is a frequency estimated as (count + prior * k) / (n + k): with little data it
stays near the prior, and it moves to the observed rate as evidence accumulates.

Stats (all from the opponent's point of view):
  vpip           put chips in voluntarily preflop (call or raise), per preflop decision hand
  pfr            raised preflop
  aggression     raises / (raises + calls), postflop
  aggression_all raises / (raises + calls), every street (catches preflop shovers)
  fold_to_raise  folded directly after one of our raises
  wtsd           reached showdown, per hand they saw a flop
Fed from neutral messages via `update(state, msg)`.

`Opponent` is what brains use: these stats, the card-inference model (bot/sim/inference.py)
and the trust in that model, behind one interface. Feed it every message (`observe`) and every
hand reconstruction (`saw`); ask it for a stat (`get`), for the trust-scaled inference model to
weight sampled worlds with (`model`), or for a range over explicit hands (`range_weights`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from bot.actions import CALL, FOLD, RAISE
from bot.log import warn
from bot.protocol import HandEnd, HandStart, Message, OppAction, Showdown
from bot.sim.inference import DEFAULTS as INFERENCE_DEFAULTS
from bot.sim.inference import Inference, Trust
from bot.strategy.oppstats import OppStats, hand_percentile
from bot.strategy.traits import TraitTests
from bot.strategy.types import TypePosterior
from bot.state import ME, GameState

DEFAULT_PRIORS = {"vpip": 0.55, "pfr": 0.25, "aggression": 0.35, "fold_to_raise": 0.40,
                  "wtsd": 0.35, "aggression_all": 0.35}


def shrink(count: float, n: float, prior: float, k: float) -> float:
    """Shrunk frequency: (count + prior * k) / (n + k)."""
    return (count + prior * k) / (n + k) if n + k > 0 else prior


@dataclass
class Counter2:
    count: int = 0
    n: int = 0

    def add(self, hit: bool) -> None:
        self.n += 1
        self.count += int(hit)


@dataclass
class OpponentModel:
    priors: dict = field(default_factory=lambda: dict(DEFAULT_PRIORS))
    k: float = 15.0
    stats: dict = field(default_factory=lambda: {s: Counter2() for s in DEFAULT_PRIORS})
    hands_seen: int = 0
    # per-hand flags
    _pre_acted: bool = False
    _vpip: bool = False
    _pfr: bool = False
    _saw_flop: bool = False
    _showdown: bool = False

    def get(self, name: str) -> float:
        c = self.stats[name]
        return shrink(c.count, c.n, self.priors.get(name, 0.5), self.k)

    def raw(self, name: str) -> tuple[int, int]:
        c = self.stats[name]
        return c.count, c.n

    def update(self, state: GameState, msg: Message) -> None:
        h = state.hand
        if isinstance(msg, HandStart):
            self._pre_acted = self._vpip = self._pfr = self._saw_flop = self._showdown = False
        elif isinstance(msg, OppAction) and h is not None and h.history:
            a = msg.action
            prev = h.history[-2] if len(h.history) >= 2 else None
            if prev is not None and prev.actor == ME and prev.action.kind == RAISE:
                self.stats["fold_to_raise"].add(a.kind == FOLD)
            if a.kind in (CALL, RAISE):
                self.stats["aggression_all"].add(a.kind == RAISE)
            if h.street == 0:
                self._pre_acted = True
                if a.kind in (CALL, RAISE):
                    self._vpip = True
                if a.kind == RAISE:
                    self._pfr = True
            else:
                self._saw_flop = True
                if a.kind in (CALL, RAISE):
                    self.stats["aggression"].add(a.kind == RAISE)
        elif isinstance(msg, Showdown):
            self._showdown = True
        elif isinstance(msg, HandEnd):
            self.hands_seen += 1
            if self._pre_acted:
                self.stats["vpip"].add(self._vpip)
                self.stats["pfr"].add(self._pfr)
            if self._saw_flop or (h is not None and h.street > 0):
                self.stats["wtsd"].add(self._showdown)


class Opponent:
    """Everything we learn about the opponent (see the module docstring)."""

    def __init__(self, inference: Optional[dict] = None, use_trust: bool = True,
                 priors: Optional[dict] = None, k: float = 15.0) -> None:
        self.base = {**INFERENCE_DEFAULTS, **(inference or {})}
        self.model = Inference(dict(self.base))     # params scaled by trust after each `saw`
        self.trust = Trust()
        self.use_trust = use_trust
        self.stats = OpponentModel(priors={**DEFAULT_PRIORS, **(priors or {})}, k=k)
        self.spots: Optional[OppStats] = None        # per-spot stats + bluff index (Tier 2 sets it)
        self.traits = TraitTests()                   # SPRT trait verdicts for the exploit layer (X1)
        self.types: Optional[TypePosterior] = None   # type posterior (X2), built on the first message
        self._types_tried = False                    # that comes with the rules
        self._last = None                            # (hand id, Reconstruction) we decided on

    @property
    def priors(self) -> dict:
        return self.stats.priors

    def get(self, name: str) -> float:
        """A shrunk frequency stat (OpponentModel)."""
        return self.stats.get(name)

    def saw(self, hand_id: int, rec) -> None:
        """Our latest reconstruction of this hand: kept for scoring at showdown, and the
        inference model is re-scaled by the current trust."""
        self._last = (hand_id, rec)
        if self.use_trust:
            self.model.params["gamma"] = float(self.base["gamma"]) * self.trust.level("bet")
            self.model.params["beta"] = float(self.base["beta"]) * self.trust.level("discard")

    def observe(self, state: GameState, msg: Message, rng, rules=None) -> None:
        """Feed one message. `rules` (the variant) lets shown hands be ranked for the bluff index."""
        self.stats.update(state, msg)
        try:                                         # observed only: nothing decides on it yet
            self.traits.update(state, msg)
        except Exception as e:
            warn(f"opponent trait tests failed: {e!r}")
        if not self._types_tried and rules is not None:
            self._types_tried = True
            try:
                self.types = TypePosterior.from_rules(rules)
            except Exception as e:
                warn(f"opponent type library not usable: {e!r}")
        if self.types is not None:
            try:
                self.types.update(state, msg)
            except Exception as e:
                warn(f"opponent type posterior failed: {e!r}")
                self.types = None
        if self.spots is not None:
            try:                                     # statistics never decide a hand's outcome
                self.spots.update(state, msg, None if rules is None else self._percentile(state, rules))
            except Exception as e:
                warn(f"opponent spot stats failed: {e!r}")
        if isinstance(msg, Showdown) and self.model.enabled and self.use_trust:
            last = self._last
            if last is None or state.hand is None or last[0] != state.hand.hand_id:
                return
            try:      # their cards are shown: how well did the model explain their choices?
                self.trust.update(self.model.decision_llr(last[1], list(msg.oppcards), rng))
            except Exception as e:
                warn(f"trust update failed: {e!r}")

    @staticmethod
    def _percentile(state: GameState, rules):
        dead = state.hand.dead_cards if state.hand is not None else ()
        return lambda hole, board: hand_percentile(rules.evaluator, hole, board, rules.deck, dead)

    def range_weights(self, rec, combos: np.ndarray, rng) -> np.ndarray:
        """Probability of each explicit opponent hand given their visible choices (sums to 1).
        combos (n, k): real cards for the opponent's k still-hidden hole tokens, in hole order.
        Hands holding a card we have seen get 0; uniform over the rest if nothing is informative."""
        combos = np.asarray(combos, dtype=np.intp)
        n = len(combos)
        hidden = [t for t in rec.state.hole[1 - rec.me] if t not in rec.mapping]
        if n == 0 or combos.shape[1] != len(hidden):
            raise ValueError(f"combos need {len(hidden)} cards per row")
        logw = self.model.log_weights(rec, {t: combos[:, i] for i, t in enumerate(hidden)}, n, rng)
        w = np.ones(n) if logw is None else np.exp(logw - logw.max())
        seen = np.array(sorted(set(rec.mapping.values())), dtype=np.intp)
        w[np.isin(combos, seen).any(axis=1)] = 0.0
        total = w.sum()
        return w / total if total > 0 else w
