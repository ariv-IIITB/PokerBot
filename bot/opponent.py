"""Everything we learn about the opponent, in one place.

`Opponent` (what the brains hold):
  in   observe(state, msg)     every engine message (stats; trust at showdowns)
       saw_hand(hand_id, rec)  the reconstruction behind each decision of ours (scored at
                               the showdown, if there is one)
  out  get(name) / stats       shrunk frequencies (below)
       inference               sample weights for simulated opponent hands
                               (bot/sim/inference.py), scaled by trust in that model

Opponent statistics with shrinkage toward priors.

Each stat is a frequency estimated as (count + prior * k) / (n + k): with little data it
stays near the prior, and it moves to the observed rate as evidence accumulates.

Stats (all from the opponent's point of view):
  vpip           put chips in voluntarily preflop (call or raise), per preflop decision hand
  pfr            raised preflop
  aggression     raises / (raises + calls), postflop
  aggression_all raises / (raises + calls), every street (catches preflop shovers)
  fold_to_raise  folded directly after one of our raises
  wtsd           reached showdown, per hand they saw a flop
Fed from neutral messages via `update(state, msg)` (Opponent.observe calls it).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from bot.actions import CALL, FOLD, RAISE
from bot.log import warn
from bot.protocol import HandEnd, HandStart, Message, OppAction, Showdown
from bot.sim.inference import Inference, Trust
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


class Opponent(OpponentModel):
    """Stats + inference + trust. `rng` is the brain's generator (trust scoring samples)."""

    def __init__(self, rng, priors: Optional[dict] = None, k: float = 15.0,
                 inference: bool = True, beta: float = 6.0, gamma: float = 3.0,
                 use_trust: bool = True) -> None:
        super().__init__(priors=dict(DEFAULT_PRIORS, **(priors or {})), k=k)
        self.rng = rng
        self.beta, self.gamma, self.use_trust = beta, gamma, use_trust
        self.inference = Inference({"enabled": inference, "beta": beta, "gamma": gamma,
                                    "ref_hands": 120, "min_ess": 0.08})
        self.trust = Trust()
        self._last = None                       # (hand id, Reconstruction) of our last decision

    def observe(self, state: GameState, msg: Message) -> None:
        self.update(state, msg)
        if isinstance(msg, Showdown) and self.inference.enabled and self.use_trust:
            self._score_showdown(state, msg)

    def saw_hand(self, hand_id: int, rec) -> None:
        self._last = (hand_id, rec)
        if self.use_trust:
            self.inference.params["gamma"] = self.gamma * self.trust.level("bet")
            self.inference.params["beta"] = self.beta * self.trust.level("discard")

    def _score_showdown(self, state: GameState, msg: Showdown) -> None:
        """Opponent cards revealed: how well did the model explain their decisions?"""
        last = self._last
        if last is None or state.hand is None or last[0] != state.hand.hand_id:
            return
        try:
            self.trust.update(self.inference.decision_llr(last[1], list(msg.oppcards), self.rng))
        except Exception as e:
            warn(f"trust update failed: {e!r}")
