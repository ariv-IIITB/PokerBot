"""Tier 4 R1: the river solver's cost against the time bank, on a machine twice as slow (README rule 3).

Tier 3 with t3_river_solver on and off play the same seed back to back on this machine, the lab engine
charging every reply double (and the solver's wall-clock box halved to match, see solver_cfg). The flag-on run must (a) use at most 1.4x the bank the flag-off run used,
(b) hit the hard deadline no more than baseline + 2 sqrt(baseline) times, (c) never need emergency mode
and stay inside the per-reply rule. Slow: ~1-4 minutes each. Run with `-m slow`."""
import math

import pytest

from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec

NO_LOCK = {"lock_enabled": False}
RATIO = 1.4
SLOWDOWN = 2.0


def solver_cfg(flag: bool) -> dict:
    """The river box is WALL-CLOCK: a server twice as slow still gives the solver 20 ms (and so ~half the passes),
    while the lab's clock_scale charges every second this laptop spends twice. To charge the box what the slow
    server would, the box here is the real one divided by the slowdown (ceiling and 4 x budget alike)."""
    from bot.timing import TimingConfig
    c = TimingConfig()
    return {"t3_river_solver": flag, "river_budget_s": c.river_budget_s / SLOWDOWN,
            "river_box_mult": c.river_box_mult / SLOWDOWN}


def run(flag: bool, hands: int, bank: float, opponent: str):
    cfg = dict(NO_LOCK, **solver_cfg(flag))
    a = PlayerSpec.brain("tier3", cfg).build()
    m = play_match([a, PlayerSpec.brain(opponent).build()], load_variant("discard_holdem"), seed=11,
                   hands=hands, time_bank_s=bank, clock_scale=SLOWDOWN, reply_limit_s=5.0)
    return m, a.bot, a.bot.brain


@pytest.mark.slow
@pytest.mark.parametrize("hands,bank", [(200, 30.0), (500, 75.0)])
@pytest.mark.parametrize("opponent", ["calling_station", "d_new_trapper"])
def test_river_solver_bank_use_and_deadline_hits_at_2x(hands, bank, opponent) -> None:
    m0, bot0, _ = run(False, hands, bank, opponent)
    m1, bot1, brain1 = run(True, hands, bank, opponent)
    for m in (m0, m1):
        assert m.forfeit is None, m.forfeit_reason
        assert m.hands_played == hands
    used0, used1 = bank - m0.bank_left[0], bank - m1.bank_left[0]
    print(f"\n{opponent} {hands}h: used {used0:.1f}s -> {used1:.1f}s (x{used1 / used0:.2f}, charged x2); "
          f"hard-deadline hits {bot0.deadline_hits} -> {bot1.deadline_hits}; worst reply "
          f"{m1.worst_decision_s[0] * 1000:.0f} ms; river solves {brain1.stats['river_solves']}, "
          f"{brain1.stats['river_iters'] / max(1, brain1.stats['river_solves']):.0f} passes each, "
          f"fallbacks {brain1.stats['river_fallbacks']}")
    assert used1 <= RATIO * used0 + 0.5, f"{used1:.1f}s vs {used0:.1f}s flag off"
    assert used1 <= 0.5 * bank, "must stay under 50 % of the bank at 2x slower"
    assert bot1.deadline_hits <= bot0.deadline_hits + 2 * math.sqrt(bot0.deadline_hits)
    assert bot1.emergency_decisions == 0, "emergency mode (Tier 0) was needed"
    assert m1.worst_decision_s[0] <= 1.5, f"a single reply took {m1.worst_decision_s[0]:.2f}s (x2)"
