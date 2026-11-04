# Tier 4 DA: smart rollouts on Tier 3 + retune (Discard Hold'em)

**Verdict: KEEP.** `bot/config/tier3.json` now sets `smart_rollout_discard: true` and `raise_equity: [0.70, 0.68, 0.68, 0.74]`
(`call_margin` stays 0.02). Machine: 14 cores, Intel Core Ultra 5 225H, shared with 3-4 other sessions (load average 25-30 during the
tuning; every eval ran under `nice -n 15`, 3-6 processes). Logs, driver and the raw tables are in `logs/da/`.

## Setup
Brain `tier3:{"smart_rollout_discard":true, ...}`, `--pool train tier1 tier2` (6 training bots + tier1 + tier2), `--variant discard_holdem`,
locks off, 400 hands, 30 pairs per point on seeds 53000-53029 (tuning), chips summed over the 8 bots. The difference to the current best is
the sum over bots of the chips/hand difference; its SE is the root of the summed squares of the per-bot SEs (as `lab.eval --compare`). A move
needs a gain > 1 SE. Driver: `logs/da/driver.py` (resumable); every move is in `logs/da/moves_dedup.log`.

## Cost (task 1)
`logs/da/timing.txt`: smart on vs off, 400 hands, 3 opponents x 2 reps, locked: bank used 48.49 s vs 46.79 s = **ratio 1.036** (limit 1.4).
Final check (`logs/da/timing_final.txt`): new shipped tier3 vs old tier3 (smart off, old thresholds), same protocol:
43.01 s vs 43.77 s = **ratio 0.98**; worst decision 20-52 ms. No "hard deadline" warning in either file (the timing harness may not show the bot's stderr).

## Tuning (30 pairs per point, seeds 53000-53029)
- Plain tier3 vs smart-on at Tier 3's values: **+0.72 ± 1.26** (no retune; noise).
- Round 1 (start `re 70-68-70-74, cm 0.02`): 
  `re[0]` 68: +0.33, 72: -0.27 | `re[1]` 66: +0.44, 70: -0.37 | `re[2]` 68: **+1.47 ± 1.24**, 72: +0.75 | `re[3]` 72: +0.37, 76: +1.33 ± 1.30 |
  `cm` 0.01: -0.47, 0.03: -0.37 (all ± 1.2). **Move: `re[2]` 0.70 -> 0.68** (+1.47 ± 1.24, z 1.2).
- Round 2 (around `70-68-68-74`): every neighbour is worse or equal: `re[0]` 68: -1.75, 72: -0.84 | `re[1]` 66: -1.06, 70: -1.22 | `re[2]` 66: -1.63,
  70: -1.47 | `re[3]` 72: -1.04, 76: +0.25 | `cm` 0.01: -1.41, 0.03: +0.83 (± 1.2). **Stop** (best +0.83 ± 1.25 is not > 1 SE).
  Rounds were capped at 3 by the manager; none was needed.
- 3 x 3 grid on the two most sensitive parameters (`re[0]` and `re[2]`, by the largest |change| in round 2), steps 0.02: all 8 neighbours worse
  (-0.84 ... -2.16, SE about 1.2). **Stay** at `70-68-68-74`, `cm 0.02`.
- Reading: with ± 1.2 per comparison nothing in the surface is distinguishable from noise except that the final point is the best of 14. The
  one move made (+1.2 SE) is a typical winner's-curse pick; that is what the fresh-seed confirmation is for.

## Confirmation (50 fresh pairs, seeds 54000-54049, new tier3 vs old plain tier3, same seeds)
Chips, locks off (`logs/da/confirm_chips.txt`): **sum +2.33 ± 0.88 (z +2.7)**. Per bot: conv_opp3 +0.44 ± 0.30, rules +0.38 ± 0.25, lag +0.96 ± 0.44
(improved), trapper +0.18 ± 0.23, exploiter +0.37 ± 0.25, minraise -0.02 ± 0.24, tier1 +0.20 ± 0.36, tier2 -0.18 ± 0.34. No bot down by > 2 SE.
Score, locks on (`lab/opps/score_compare.py`, `logs/da/confirm_score.txt`): mean 0.641 -> 0.648, **+0.006 ± 0.022 (z +0.3)** -> KEEP-score.
Two-part rule: **KEEP**. (50 pairs, one run, as the manager's light-testing rule asked.)

Not separated: how much of the +2.33 is smart rollouts alone and how much the `re[2]` 0.68 change (at the tuning seeds the
smart-on-default point was +0.72 ± 1.26 over plain and the final point +1.47 ± 1.24 over that). Both ship together.

## Deadline warnings in the tuning logs
`logs/da/deadline_hits.txt`: warnings "brain exceeded hard deadline" by point, mostly in loaded periods: the plain reference (smart off) had 185, the smart-on
start point 27, other points 1-344. They track machine load, not the flag. Confirmation logs: 0 / 0 / 0 (chips and plain score) and 7 in the smart-on
locks-on run. Decisions are not logged; per 1000 decisions the table assumes about 864k decisions per point (4.5 of ours per hand).
Unloaded and locked: none seen in `timing_final.txt`.

## Shipped change
`bot/config/tier3.json` (new) -> `bot/embedded.py` regenerated. `tier3x` and anything else with `param_file = "tier3"` reads the same file,
so they inherit these values. Tests: `tests/test_tier3.py` (the new values; the Tier 2 equality test now skips keys tier3.json sets).
Fast suite: 1291 passed, 2 skipped.
