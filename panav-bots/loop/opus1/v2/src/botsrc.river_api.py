# botsrc/river_api.py — shared contract, both of you code against it
from dataclasses import dataclass
import numpy as np

@dataclass
class RiverContext:
    hand_id: int
    seat: str                    # "button" | "big_blind"
    board: list                  # 5 card ids (§4.1)
    hole: list                   # our 2 kept cards
    my_discard: int
    opp_discard: int
    pot: int                     # protocol fields from the current action_request
    my_bet: int
    opp_bet: int
    to_call: int
    my_stack: int
    opp_stack: int
    legal_actions: list
    min_raise: int | None
    max_raise: int | None
    raises_left: int
    pot_at_river_start: int
    river_history: list          # river actions so far, protocol format
    my_range: np.ndarray         # float64[1326], idx2 order: opponent's view of us at river START
    opp_range: np.ndarray        # float64[1326]: our view of the opponent at river START
    time_budget_ms: float        # hard budget for this call
    blueprint_dist: dict         # our RIVER-table distribution over legal slots (fallback / warm start)
    opp_model: dict | None       # opponent summary from the exploit layer (hooks.opp_model()), or None
    # Optional, filled only when the build bundles the river solver (Phase 10): both ranges NOW, i.e.
    # also given the river actions so far (§9.6; the opponent's is the range the river all-in rule
    # uses, through the blueprint RIVER table; in ours, an action the solver chose counts with the
    # solver's own strategy for it, any other with the RIVER table). A solver that starts at the
    # current decision needs these.
    my_range_now: np.ndarray | None = None
    opp_range_now: np.ndarray | None = None
    # Optional, F-fold builds only: (answered, folds), the opponent's answers to our river bets and
    # raises in this leg so far (a call or a raise counts as not folding).
    opp_river_folds: tuple | None = None

def decide(ctx: RiverContext) -> list | None:
    """Return a distribution over legal actions, e.g.
    [{"action": "call", "amount": None, "p": 0.7}, {"action": "raise", "amount": 40, "p": 0.3}],
    or None to use the blueprint. "amount" is the raise-to total for "raise", else None.
    Anytime: a usable answer within 50 ms, better answers with more of ctx.time_budget_ms,
    never past ctx.time_budget_ms. May cache per hand_id."""
    # Phase 7: river_stub always returns None (use the blueprint). Phase 10: builds with the solver
    # flag on route here to the glue around the teammate's solver (botsrc/river_glue.py).
    if _SOLVER is not None:
        return _SOLVER.decide(ctx)
    try:
        from . import river_stub
    except ImportError:          # imported as a top-level module (the river kit): no stub, no solver
        return None
    return river_stub.decide(ctx)


_SOLVER = None                   # set by use() at start-up when the build bundles the river solver


def use(module):
    """Route decide() to module.decide (botsrc.river_glue); None restores the stub."""
    global _SOLVER
    _SOLVER = module
