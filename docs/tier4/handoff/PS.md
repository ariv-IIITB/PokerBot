# Handoff PS (portfolio on top of O3)

**Verdict: DROP the portfolio. `tier4p` stays out of `tier4/int`.** Stopped early by the manager (user decision); the run was not finished.
**Branch** `tier4/ps`. A = `tier3x` (tier4/int, O3 on), B = `tier4p` auto, now built on `Tier3XBrain` (all members inherit `x_narrow`, `x_air_eq` 0.45; base member = `tier3x`). `tests/test_tier4p.py::test_members_inherit_o3_river_rules`; fast suite 1362 passed, 2 skipped. Merge of `origin/tier4/pd` resolved in `bot/brains/exploit.py` (O3 rules kept in `apply_overfolder`).
**Setup:** discard_holdem, 50 pairs per bot, seeds 74000, `--processes 3`, laptop locks. Driver `logs/ps/ps_gate.py`, results `logs/ps/runs/`. The laptop rebooted mid-run (one run cut off was redone).

Chips/hand, locks off, B - A (completed: all 5 bots):
conv_opp3 +0.05 ± 0.19, exploiter +0.09 ± 0.17, lag -0.45 ± 0.40, minraise -0.02 ± 0.18, trapper +0.31 ± 0.19.
Sum -0.02 ± ~0.54 (z ~0): flat. No bot down by more than 2 SE, but nothing up either.
Match score, locks on (3 of 5 bots finished: A -> B): conv_opp3 0.630 -> 0.660, lag 0.970 -> 1.000, trapper 0.970 -> 0.980 (all ±0.02-0.05, within noise).
Not run (stopped): locks-on exploiter and minraise, head to head B vs A, member-selection counts, timing.

Reading: on top of O3 the PD gains (trapper, minraise, maniac) shrink to noise (trapper +0.31 vs +1.66 before); nothing vs the strong bots. The portfolio adds no evidence of value, so remove it from the ship stack.
