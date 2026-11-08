"""Trait tests on the opponent: fast yes/no verdicts for the exploit layer (build map X1).

Each trait is a Bernoulli rate the opponent shows at one kind of decision. Wald's sequential
probability ratio test (book §1.4.2) decides between two rates as soon as the evidence allows
(error rates alpha = beta = 0.05). Once decided, a CUSUM (book §1.9.3) watches for evidence of
the other rate; an alarm makes the trait undecided again and restarts it, so a bot that changes
style is noticed.

  overfolder      folds, per decision facing our postflop bet or raise      0.40 vs 0.60
  overfolder_tr   the same, turn and river only (un-pooled from the flop:
                  a bot's true rate there can sit far from either, diluting
                  the pooled test; the exploit layer takes whichever test
                  decides first)                                            0.40 vs 0.60
  station         continues (calls or raises), per decision facing our
                  river bet or raise                                        0.50 vs 0.80
  preflop_folder  folds to our preflop open (our first-in raise)            0.35 vs 0.55

Fed from the same message stream as bot/opponent.py (`update(state, msg)`); nothing here decides
an action. Rates are also given shrunk toward the prior (as oppstats: K = 15).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

from bot.protocol import Message, OppAction
from bot.state import ME, OPP, ActionRecord, GameState

BETTING = frozenset("FKCR")
ALPHA = BETA = 0.05
UPPER = math.log((1 - BETA) / ALPHA)          # decide "yes" (H1)
LOWER = math.log(BETA / (1 - ALPHA))          # decide "no" (H0)
CUSUM_H = 5.0                                 # alarm threshold, in nats
SHRINK_K = 15.0


@dataclass(frozen=True)
class TraitSpec:
    p0: float        # the "no" rate (H0)
    p1: float        # the "yes" rate (H1)
    prior: float     # shrinkage target


SPECS: dict[str, TraitSpec] = {
    "overfolder": TraitSpec(0.40, 0.60, 0.40),
    "overfolder_tr": TraitSpec(0.40, 0.60, 0.40),
    "station": TraitSpec(0.50, 0.80, 0.50),
    "preflop_folder": TraitSpec(0.35, 0.55, 0.35),
}


@dataclass(frozen=True)
class Event:
    """One opponent betting decision, in the context the traits need."""
    street: int
    kind: str                # F K C R
    facing: bool             # the last bet or raise on this street was ours
    vs_open: bool            # preflop: its first answer to our first-in raise


def classify(history: Sequence[ActionRecord]) -> Optional[Event]:
    """The Event for the last action in `history` if it is an opponent betting action."""
    if not history:
        return None
    last = history[-1]
    if last.actor != OPP or last.action.kind not in BETTING:
        return None
    street = last.street
    prior = [r for r in history[:-1] if r.street == street and r.action.kind in BETTING]
    raises = [r for r in prior if r.action.kind == "R"]
    facing = bool(raises) and raises[-1].actor == ME
    vs_open = (street == 0 and len(prior) == 1 and prior[0].actor == ME
               and prior[0].action.kind == "R")
    return Event(street, last.action.kind, facing, vs_open)


def observations(ev: Event) -> dict[str, bool]:
    """Which traits this decision is evidence for, and the outcome (True = the H1 behaviour)."""
    out: dict[str, bool] = {}
    if ev.facing and ev.street >= 1:
        out["overfolder"] = ev.kind == "F"
        if ev.street >= 2:
            out["overfolder_tr"] = ev.kind == "F"
        if ev.street == 3:
            out["station"] = ev.kind in ("C", "R")
    if ev.vs_open:
        out["preflop_folder"] = ev.kind == "F"
    return out


@dataclass
class SPRT:
    """One trait: SPRT until decided, then a CUSUM against the other rate."""
    spec: TraitSpec
    llr: float = 0.0
    verdict: str = "open"            # open | yes | no
    hits: int = 0                    # since the last restart
    n: int = 0
    cusum: float = 0.0
    alarms: int = 0
    decided_at: Optional[int] = None  # observation count (since the restart) at the verdict
    total: int = 0                    # observations ever
    _step: tuple = field(init=False, repr=False)

    def __post_init__(self) -> None:
        p0, p1 = self.spec.p0, self.spec.p1
        # log P(x | H1) / P(x | H0) for x = 1 and x = 0
        self._step = (math.log((1 - p1) / (1 - p0)), math.log(p1 / p0))

    def add(self, x: bool) -> None:
        self.total += 1
        self.n += 1
        self.hits += int(x)
        step = self._step[int(x)]
        if self.verdict == "open":
            self.llr += step
            if self.llr >= UPPER:
                self.verdict, self.decided_at = "yes", self.n
            elif self.llr <= LOWER:
                self.verdict, self.decided_at = "no", self.n
            return
        # decided: evidence for the other hypothesis accumulates
        self.cusum = max(0.0, self.cusum + (-step if self.verdict == "yes" else step))
        if self.cusum > CUSUM_H:
            self.alarms += 1
            self.restart()

    def restart(self) -> None:
        self.llr, self.verdict, self.hits, self.n = 0.0, "open", 0, 0
        self.cusum, self.decided_at = 0.0, None

    @property
    def rate(self) -> float:
        """The rate since the last restart, shrunk toward the prior."""
        return (self.hits + self.spec.prior * SHRINK_K) / (self.n + SHRINK_K)


@dataclass(frozen=True)
class TraitState:
    verdict: str
    llr: float
    rate: float
    n: int
    alarms: int


class TraitTests:
    """All trait tests for one opponent. Feed every message with `update`."""

    def __init__(self, specs: Optional[dict[str, TraitSpec]] = None) -> None:
        self.tests = {name: SPRT(s) for name, s in (specs or SPECS).items()}

    def update(self, state: GameState, msg: Message) -> None:
        h = state.hand
        if isinstance(msg, OppAction) and h is not None:
            ev = classify(h.history)
            if ev is not None:
                self.observe(ev)

    def observe(self, ev: Event) -> None:
        for name, x in observations(ev).items():
            test = self.tests.get(name)
            if test is not None:
                test.add(x)

    def verdict(self, name: str) -> str:
        return self.tests[name].verdict

    def state(self) -> dict[str, TraitState]:
        return {name: TraitState(t.verdict, t.llr, t.rate, t.n, t.alarms)
                for name, t in self.tests.items()}
