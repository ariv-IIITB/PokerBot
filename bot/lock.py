"""Endgame lock: once our match lead is bigger than the most we could lose by check/folding
every remaining hand, we only check/fold (a guaranteed match win). Bot.choose (bot/main.py)
applies it above every brain that turns it on (Brain.lock_enabled), next to emergency mode.
"""
from __future__ import annotations

from typing import Optional

from bot.state import GameState


def lock_margin(state: GameState, assume_alternating: bool = True, rules=None) -> Optional[int]:
    """Lead minus the worst-case loss from check/folding the rest of the match.

    Worst case = what we've already put in this hand (lost if we fold now) + the forced
    bets we post in every future hand (ante + our blind, or the straddle). Our seat
    alternates each hand (seat 0 = small blind), as in a duplicate match; with
    assume_alternating=False every future hand costs the bigger forced bet. Blind
    schedules come from `rules` (the compiled variant) when known.
    > 0 means the match is mathematically won by check/folding. None if unknown.
    """
    h, m = state.hand, state.match
    if h is None or h.finished:
        return None
    committed = h.start_stack - h.my_stack
    future = max(0, m.hands - state.hands_played - 1)
    first_future = h.hand_id + 1

    def costs(j: int) -> tuple[int, int]:
        """(small-blind seat cost, big-blind seat cost) for future hand j."""
        if rules is not None and hasattr(rules, "level_at"):
            sb, bb, ante, straddle = rules.level_at(first_future + j - 1)
        else:
            sb = h.sb if h.sb is not None else m.sb
            bb = h.bb if h.bb is not None else m.bb
            ante, straddle = h.ante or 0, 0
        return ante + (straddle or sb), ante + bb

    cost = 0
    for j in range(1, future + 1):
        sb_cost, bb_cost = costs(j)
        if assume_alternating:
            cost += sb_cost if (h.seat + j) % 2 == 0 else bb_cost
        else:
            cost += max(sb_cost, bb_cost)
    return state.bankroll - committed - cost
