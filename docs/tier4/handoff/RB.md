# RB handoff: the river solver inside Tier 3

**Done, flag off by default.** Branch `claude/subplan-xx-execution-g00q9v` (assigned instead of `tier4/r`; built on RA's branch
`claude/zen-ptolemy-4w0rqi`, since `tier4/r` doesn't exist). Commit: see `git log -1` on the branch. Machine: Intel Xeon @ 2.10 GHz, nproc 4, Py 3.11.
Step 0: RA's GO holds here: 64 buckets, 1 / all-in tree, **136 passes median in a 20 ms box** (81 % of spots >= 100; bar 100).

## What it is
* `t3_river_solver` (default **false**; flag off = identical play and identical `stats` keys). On, every river decision (2 hole cards, a
  reconstruction, street bets known) builds both ranges and solves in ONE box = min(`river_box_mult` 4 x budget, `river_budget_s` 0.020), then
  samples the root strategy of our hand's bucket. Lock first (unchanged). Fallback to Tier 3's river on exception, no pass fitting,
  < `river_min_iters` 20, or a missing piece. Counters (only with the flag on): `river_solves/iters/us/fallbacks/errors/few_iters/no_pass/missing`.
* **Ranges are random samples of 300 combos per side** (`river_combos`; ours always holds our hand) and the solve stops at 150 passes
  (`river_max_iters`). Full 990/903 ranges + setup cost 12 ms here, so at 2x slower nothing fit in the box (first attempt: 9 passes, 75 % fallbacks,
  1.49x bank). Sampled: ranges ~4.5 ms + setup ~1 ms.
* `bot/strategy/own_range.py` (`own_range_weights`): our line (every bet/check/call/raise + the discard) scored with Inference's own bet and
  discard likelihoods at default parameters (no trust), the hand scored as X + our public discard before the discard. Approximation, said in
  its docstring. Tests: a raising line favours trips over air, more than a checking line; board/discarded cards get 0; uniform with no line.
* `bot/timing.py`: `river_budget_s`, `river_box_mult`, `TimeManager.river_box()`. The box (<= 20 ms) is always < max(80 ms, 6 x budget) and
  hard deadline >= 2 x box for every bank/hands state outside emergency mode (tested), so **the hard limit was not raised**.
* **Touched a file outside the R row:** `bot/sim/replay.py` records our own decisions (`Reconstruction.my_decisions`, 4 lines, additive).

## Numbers (logs/river_timing_RB.txt, river_smoke_RB*.txt, river_sensitivity_RB.txt, rb_timing_slow.txt)
* **Timing at 2x slower** (clock x2, solver box halved because the real box is wall-clock; flag on / flag off, same seed, lock off):
  calling_station 400h 22.1 s vs 17.2 s (x1.28), trapper 400h 13.1 vs 10.4 (x1.26); 1000h x1.23 (53.3 vs 43.4 s of 150) and x1.24 (33.3 vs 26.8).
  Rule <= 1.4: met. Hard-deadline hits 0 in all 8 runs (baseline 0). Worst reply 94 ms. `test_timing_slow.py` 10 passed. Fast suite 1323 passed, 2 skipped.
  At 2x the solver gets **~37-42 passes** per decision (RA's table: 50 passes = 0.029 pot exploitability, 100 = 0.015) and 12-25 % of river decisions fall back.
* **Sensitivity** (200 spots, root EV of our hand in pots, flat vs built own range): |change| mean **0.146 ± 0.022**, median 0.033, p90 0.365,
  **20 % of spots above 0.20 pot**; root strategy TV distance 0.19 ± 0.02. Mean is under the 20 % bar, so not declared the weak point,
  but one spot in five moves more than 0.2 pot: **RC should read gate R with the own range as the main caveat.**
* **Smoke** (8 pairs, 400h, locks off, laptop speed, seeds 60000+, not a gate), chips/hand flag on vs off: conv_opp3 -1.06 ± 0.50 vs -0.77 ± 0.45
  (score 0.25 vs 0.375); trapper -0.07 ± 0.42 vs +0.30 ± 0.28 (0.50 vs 0.56). No sign of a gain at this size. Iterations per decision **131 (conv_opp3),
  129 (trapper)**, mean 18.2 / 18.6 ms per solve; fallbacks 2 of 2615 and 6 of 3871 (none from errors).

## For RC / later
* Gate R must be run with the box halved (README), where the solver has ~40 passes and the own range matters; expect it to be marginal.
* Levers if it isn't: cheaper ranges (the 120-hand reference draw inside `Inference.strength` is ~2 ms per range, D's file), a shorter box, or
  skipping the solver in spots it can't change (nuts/air unfaced). Tree is 1 x pot + all-in; no value-floor/equity-floor guards on solver actions.
