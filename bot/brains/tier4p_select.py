"""Member selection for tier4p in "auto" mode (PC; docs/TIER4_PLAN.md P2).

`choose_member(brain, street)` is called by Tier4PBrain on every non-locked decision and returns one of
tier4p.MEMBER_NAMES. The member is chosen once per hand (at our first decision of the hand) and kept for
that hand, except that a bail-out switches an over-folder member off at once. Rules:

  Selection  F = the X2 family with the most posterior mass. over-folder -> anti_folder; value-only and
             trapper -> anti_value; aggressor -> anti_aggro; unknown, nit, station -> base.
             F's member plays only if mass(F) >= MASS_MIN at each of our last WINDOW decisions (the same F
             every time) and: anti_folder: X1's over-folder SPRT says "yes"; anti_value / anti_aggro:
             at least MIN_OBS opponent decisions seen. Otherwise base.
  Bail-out   a new X1 over-folder CUSUM alarm -> base for that hand, and anti_folder is blocked for
             BLOCK_HANDS hands (completed hands, locked ones included).
  Stop-loss  checked once at each of 25 / 50 / 75 % of total_hands: if our chips since the current non-base
             member switched on are below 0 by more than 2 SE (per-hand SD measured in this match), play
             returns to base for the rest of the match.
  Lock       the endgame lock runs before all of this (Tier2.decide), so locked hands never reach here.
             If a lock occurred since the member switched on, the match is already won and the
             stop-loss is not applied.

Any error -> "base" (counted in brain.stats["p_errors"]). The state lives on the brain instance.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any, Optional

from bot.log import warn

FAMILY_MEMBER = {"overfolder": "anti_folder", "valueonly": "anti_value", "trapper": "anti_value",
                 "aggressor": "anti_aggro"}
MASS_MIN = 0.8            # posterior mass of the family ...
WINDOW = 20               # ... at each of our last this many decisions
MIN_OBS = 60              # opponent decisions seen (anti_value, anti_aggro)
BLOCK_HANDS = 50          # anti_folder stays off this many hands after a CUSUM alarm
CHECKPOINTS = (0.25, 0.50, 0.75)
STOP_SE = 2.0
MIN_BLOCKS = 10           # hand samples needed before the SD is trusted


class _Sel:
    """Selection state of one match (one per brain)."""

    def __init__(self) -> None:
        self.hist: deque = deque(maxlen=WINDOW)    # top family with mass >= MASS_MIN at each decision, else None
        self.hand_id: Any = None
        self.member = "base"                        # member for the current hand
        self.alarms_seen = 0
        self.blocked_until = -1                     # anti_folder blocked while hands_played < this
        self.stopped = False                        # stop-loss fired: base for the rest of the match
        self.checked = [False, False, False]
        # chips per observed block (a block is one hand, or several if hands without a decision of ours
        # fall between two observed ones): (hands, chips)
        self.blocks: list[tuple[int, int]] = []
        self.last_hp: Optional[int] = None          # hands_played at the previous hand start
        self.last_bank = 0
        self.switch_bank = 0                        # bankroll / hands_played / lock count when the member switched on
        self.switch_hp = 0
        self.switch_locks = 0
        self.prev_member = "base"


def _game_state(brain):
    """The GameState the brain is deciding on (the Situation built for this decision holds it)."""
    st = getattr(brain, "state", None)
    if st is not None:
        return st
    cur = brain.perception._current
    return cur[1].state


def _sd(blocks: list[tuple[int, int]]) -> Optional[float]:
    """Per-hand SD of chips from the observed blocks (residuals scaled by block length)."""
    if len(blocks) < MIN_BLOCKS:
        return None
    k = sum(b[0] for b in blocks)
    mean = sum(b[1] for b in blocks) / k
    ss = sum((c - n * mean) ** 2 / n for n, c in blocks)
    return math.sqrt(ss / (len(blocks) - 1))


def _stop_loss_hit(sel: _Sel, gs, brain) -> bool:
    """True if our chips since the member switched on are below 0 by more than 2 SE."""
    if sel.prev_member == "base" or getattr(brain, "locked_decisions", 0) > sel.switch_locks:
        return False
    n = gs.hands_played - sel.switch_hp
    sd = _sd(sel.blocks)
    if n <= 0 or sd is None:
        return False
    net = gs.bankroll - sel.switch_bank
    return net < -STOP_SE * sd * math.sqrt(n)


def _new_hand(sel: _Sel, gs, brain) -> None:
    """Bookkeeping at our first decision of a hand."""
    hp = gs.hands_played
    if sel.last_hp is not None and hp < sel.last_hp:      # a new match on the same brain
        fresh = _Sel()
        sel.__dict__.update(fresh.__dict__)
    if sel.last_hp is not None and hp > sel.last_hp:
        sel.blocks.append((hp - sel.last_hp, gs.bankroll - sel.last_bank))
    sel.last_hp, sel.last_bank = hp, gs.bankroll
    total = int(getattr(gs.match, "hands", 0) or 0)
    if total > 0 and not sel.stopped:
        for i, frac in enumerate(CHECKPOINTS):
            if not sel.checked[i] and hp >= math.ceil(frac * total):
                sel.checked[i] = True
                if _stop_loss_hit(sel, gs, brain):
                    sel.stopped = True
                    brain.stats["sel_stoploss"] = brain.stats.get("sel_stoploss", 0) + 1


def choose_member(brain, street: int) -> str:
    try:
        return _choose(brain)
    except Exception as e:                       # selection must never cost a hand: Tier 3
        brain.stats["p_errors"] = brain.stats.get("p_errors", 0) + 1
        warn(f"tier4p selection failed: {e!r}")
        return "base"


def _choose(brain) -> str:
    gs = _game_state(brain)
    h = gs.hand
    sel: _Sel = brain.__dict__.setdefault("_sel", _Sel())
    opp = brain.opponent
    types, traits = opp.types, opp.traits

    # evidence at this decision (every decision, not only the first of a hand)
    fams = types.families() if types is not None else {}
    top = max(fams, key=fams.get) if fams else None
    sel.hist.append(top if top is not None and fams[top] >= MASS_MIN else None)

    # bail-out: a new over-folder CUSUM alarm
    t_of = traits.tests.get("overfolder") if traits is not None else None
    alarmed = t_of is not None and t_of.alarms > sel.alarms_seen
    if alarmed:
        sel.alarms_seen = t_of.alarms
        sel.blocked_until = gs.hands_played + BLOCK_HANDS
        brain.stats["sel_bailouts"] = brain.stats.get("sel_bailouts", 0) + 1

    new_hand = sel.hand_id != h.hand_id
    if new_hand:
        _new_hand(sel, gs, brain)
        sel.hand_id = h.hand_id
        sel.member = _pick(sel, gs, types, t_of, n_obs=types.n if types is not None else 0)
        if sel.member != sel.prev_member:
            sel.switch_bank, sel.switch_hp = gs.bankroll, gs.hands_played
            sel.switch_locks = getattr(brain, "locked_decisions", 0)
            brain.stats["sel_switches"] = brain.stats.get("sel_switches", 0) + 1
            sel.prev_member = sel.member
    elif alarmed and sel.member == "anti_folder":
        sel.member = "base"                      # the over-folder premise just failed: stop at once
        sel.prev_member = "base"
    return "base" if sel.stopped else sel.member


def _pick(sel: _Sel, gs, types, t_of, n_obs: int) -> str:
    if sel.stopped or types is None or len(sel.hist) < WINDOW:
        return "base"
    fam = sel.hist[0]
    if fam is None or any(f != fam for f in sel.hist):
        return "base"
    member = FAMILY_MEMBER.get(fam, "base")
    if member == "anti_folder":
        if gs.hands_played < sel.blocked_until or t_of is None or t_of.verdict != "yes":
            return "base"
    elif member != "base" and n_obs < MIN_OBS:
        return "base"
    return member
