"""Hooks for the exploit layer (BUILDMAP §9.9): botsrc/exploit.py behind the same names and signatures.
Every function has a safe default: with the layer off (build config "exploit" off, the default), or with
no move on ("track"), they change nothing, so the bot plays exactly as without the layer.

Rules for the layer (the bot enforces the cap and the time budget as a safety net):
  - strength n / (n + 50) for an adjustment backed by n observations (the layer ramps after its tests)
  - act only on deviations from the blueprint baseline larger than 2 standard errors (sequential tests)
  - shift each decision by at most 0.3 total variation from the incoming distribution
  - at most 5 ms per decision (exploit_adjust plus its share of on_event)
"""
from . import exploit as X

DEFAULT_TAU = 0.7


def setup(config, abstraction=None):
    """Called once by the policy with the build config (key "exploit": off | track | moves, see exploit.py)."""
    X.setup(config, abstraction)


def on_event(msg):
    """Called with every engine message (dict), for opponent modelling."""
    X.on_event(msg)


def exploit_adjust(ctx, dist):
    """dist: {label: probability} over the legal options (ctx.options). Return a new distribution."""
    return X.adjust(ctx, dist)


def solver_opp_range(range_now, range_start, board, req, hand_id):
    """The opponent range handed to the river solver: a new float64[1326], or None to keep range_now.
    Only the solver's input changes, never its logic."""
    return X.solver_opp_range(range_now, range_start, board, req, hand_id)


def exploit_summary():
    """One dict for the match-end log line (None with the layer off)."""
    return X.summary()


def opp_model():
    """A small dict summarising the opponent for the river solver (ctx.opp_model), or None."""
    return None


def range_tau():
    """Opponent-range tempering exponent (§9.6), in (0, 1]. Our own range is never tempered."""
    return DEFAULT_TAU


def opp_action_likelihood(action):
    """Optional §9.6 range factor: float64[1326] over the opponent's candidate pairs, or None."""
    return None
