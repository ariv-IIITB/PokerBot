"""Time bank management: per-decision budgets, emergency mode and a hard deadline.

Budget = usable bank / (hands left * expected decisions per hand) / safety factor.
The bank and hand count come from the MATCH message (never hardcoded); the bank left comes
from the engine's time_left on every request, so the budget follows the real clock.

Measured on discard_holdem (Phase D): a hand takes ~5.1-5.6 decisions of ours (preflop, flop,
discard, turn, river and every re-raise), and a brain that spends its whole budget uses
usable / safety of the bank. safety 5.5 keeps that near 20 %, so a server 2x slower still lands
under 50 %, and the lab's slow-machine test (engine charges every reply double) checks it.

The hard limit is the last line of defence for the 5 s per-reply rule: it never exceeds
0.3 x per_response (1.5 s for the default 5 s), whatever the bank says.

The hard deadline uses SIGALRM (Unix, main thread only). If a brain overruns, the alarm
raises `DeadlineExceeded` inside it and the main loop falls back to Tier 0. Where signals
aren't available the deadline is a no-op and brains must respect their budget themselves.
"""
from __future__ import annotations

import signal
import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class TimingConfig:
    decisions_per_hand: float = 5.5   # measured: 5.1-5.6 on discard_holdem (the discard counts)
    safety_factor: float = 5.5        # slack for a slower server and fixed per-decision costs
    reserve_frac: float = 0.10        # bank fraction never planned for
    max_budget_s: float = 0.25        # cap for any single decision
    catch_up_cap: float = 1.2         # ...and x the opening pace: a bank saved early is not spent late
    emergency_floor_s: float = 1.0    # emergency if bank below max(floor, frac * bank)
    emergency_frac: float = 0.05
    hard_mult: float = 6.0            # hard deadline = max(hard_min, budget * mult)
    hard_min_s: float = 0.08
    hard_bank_frac: float = 0.25      # ...but never more than this share of the bank left
    hard_cap_s: float = 1.5           # ...nor than this
    hard_reply_frac: float = 0.3      # ...nor than this share of the per-reply limit
    default_reply_s: float = 5.0      # per-reply limit when the engine doesn't say
    river_budget_s: float = 0.040     # ceiling of the river solver's time box (Tier 3's t3_river_solver)
    river_box_mult: float = 3.9       # ...whose box is min(this x the decision budget, river_budget_s)
    retry_deadline_s: float = 0.030   # the budget-0 brain retry after a deadline hit or error (bot/main.py retry_cheap)


class TimeManager:
    def __init__(self, bank_s: float = 60.0, hands: int = 400,
                 cfg: Optional[TimingConfig] = None) -> None:
        self.cfg = cfg or TimingConfig()
        self.configure(bank_s, hands)

    def configure(self, bank_s: float, hands: int, per_response_s: Optional[float] = None) -> None:
        """Called on MATCH: reset for a match of `hands` hands and a `bank_s` bank.
        per_response_s: the engine's limit for any single reply (init's per_response_ms)."""
        self.bank_total = float(bank_s)
        self.hands_total = int(hands)
        c = self.cfg
        # The opening pace. Without a cap the formula spends savings late (budgets grow as hands
        # run out), so a match used ~50 % of the bank instead of ~30 %, and the last hands ran
        # 10x the budget of the first: exactly what a slow server cannot absorb.
        self.pace_s = (1.0 - c.reserve_frac) * self.bank_total / max(1, self.hands_total) \
            / c.decisions_per_hand / c.safety_factor
        self.reply_s = float(per_response_s) if per_response_s else self.cfg.default_reply_s
        self._engine_left: Optional[float] = None  # latest engine-reported bank
        self._used_since_report = 0.0              # our own time since that report
        self._used_total = 0.0

    # ---- bookkeeping
    def observe_timeleft(self, timeleft: Optional[float]) -> None:
        """Engine's view of our bank is authoritative whenever it's sent."""
        if timeleft is not None:
            self._engine_left = float(timeleft)
            self._used_since_report = 0.0

    def add_used(self, seconds: float) -> None:
        """Record time we spent deciding (used when the engine doesn't report the bank)."""
        self._used_since_report += seconds
        self._used_total += seconds

    @property
    def bank_left(self) -> float:
        if self._engine_left is None:
            base = self.bank_total - self._used_total
        else:
            base = self._engine_left - self._used_since_report
        return max(0.0, base)

    # ---- decisions
    def emergency_threshold(self) -> float:
        return max(self.cfg.emergency_floor_s, self.cfg.emergency_frac * self.bank_total)

    def emergency(self) -> bool:
        """True when the bank is so low only the cheapest play is safe."""
        return self.bank_left < self.emergency_threshold()

    def budget(self, hands_remaining: int) -> float:
        """Seconds this decision may use (soft target the brain should respect)."""
        c = self.cfg
        usable = self.bank_left - c.reserve_frac * self.bank_total
        if usable <= 0:
            return 0.0
        per = usable / (max(1, hands_remaining) * c.decisions_per_hand) / c.safety_factor
        return min(per, c.max_budget_s, c.catch_up_cap * self.pace_s)

    def river_box(self, budget_s: float) -> float:
        """Wall-clock seconds the river solver may use (ranges + solve) for a decision with budget `budget_s`.
        Always below the hard deadline: hard_limit is max(hard_min_s, 6 x budget) unless capped by the
        bank (emergency mode starts long before that), and this is min(3.9 x budget, 40 ms) < both."""
        return max(0.0, min(self.cfg.river_box_mult * budget_s, self.cfg.river_budget_s))

    def hard_limit(self, budget_s: float) -> float:
        """Wall-clock cutoff after which the brain is interrupted."""
        c = self.cfg
        cap = min(c.hard_cap_s, c.hard_reply_frac * self.reply_s)
        return min(max(c.hard_min_s, budget_s * c.hard_mult), cap, c.hard_bank_frac * self.bank_left)


# --------------------------------------------------------------------------- hard deadline

class DeadlineExceeded(BaseException):
    """Raised inside a brain when its hard deadline passes. BaseException on purpose, so a
    brain's own `except Exception` can't swallow it."""


_armed = False
_installed = False


def _on_alarm(signum, frame) -> None:  # pragma: no cover - timing dependent
    # The handler stays installed for the whole run; it only fires while armed. This
    # avoids ever restoring SIG_DFL (which would kill the process on a late signal).
    if _armed:
        raise DeadlineExceeded()


def deadline_supported() -> bool:
    return hasattr(signal, "setitimer") and threading.current_thread() is threading.main_thread()


class hard_deadline:
    """Context manager: `with hard_deadline(0.05): brain.decide(...)`."""

    def __init__(self, seconds: float) -> None:
        self.seconds = max(0.001, float(seconds))
        self.active = False

    def __enter__(self) -> "hard_deadline":
        global _armed, _installed
        if deadline_supported():
            if not _installed:
                signal.signal(signal.SIGALRM, _on_alarm)
                _installed = True
            _armed = True
            signal.setitimer(signal.ITIMER_REAL, self.seconds)
            self.active = True
        return self

    def __exit__(self, *exc) -> bool:
        global _armed
        if self.active:
            _armed = False  # disarm first: a signal arriving now is ignored
            signal.setitimer(signal.ITIMER_REAL, 0)
        return False


class Stopwatch:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self.t0
