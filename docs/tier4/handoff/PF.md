# PF handoff: step 1 = NO-GO (no chart built, flag `t3_preflop_chart` not added, `bot/` untouched)

Branch `tier4/pf` (cut from `tier4/r` 2cb7bbf). Machine: laptop, 14 cores, load ~17, 1 process, nice 19. Seeds 60000-60019.
Data: S0 recordings (`origin/tier4/s0`, Tier 3, 12 pairs = 9,600 hands per bot). `d_new_rules` and held-out bots were not analysed or cited.

## Step 1 numbers (scripts in `logs/pf/step1_*.py`, probe in `logs/pf/probe_*.txt`)
* **Steals and folds do not leak.** Tier 3 opens ~80 % of its button hands (limps 9-19 %), folds as big blind 6-18 % of the time.
  Preflop-ended hands pay +0.25..+0.69 chips/hand vs the over-folders (conv_opp3, exploiter, minraise, trapper, tight); our folds cost
  0.01..0.18 chips/hand in total. Converting every limp to a raise is worth < 0.1 net once the 64-89 % that do not fold are counted.
* **The one big channel is 3-bet pots we call.** When they 3-bet and we see a flop: conv_opp3 0.037/h, mean -18.6 per pot (-0.70/h);
  exploiter 0.029/h, -19.6 (-0.56/h). This is gross loss, mostly postflop, not a preflop leak by itself.
* **Probe: does the preflop lever move chips?** `tier3` with `pf_btn_continue` (our continue share vs a 3-bet) 0.35 / 0.60 (default) / 0.85
  (0.85 with `pf_ratio_slope` 0), 20 pairs, locks off, `lab.eval`, chips/hand ± SE (score in brackets):
  | vs | 0.35 | 0.60 | 0.85 |
  |---|---|---|---|
  | conv_opp3 | -1.17 ± 0.30 (0.29) | -1.25 ± 0.26 (0.30) | -1.07 ± 0.24 (0.18) |
  | exploiter | -0.99 ± 0.25 (0.35) | -1.05 ± 0.31 (0.28) | -0.61 ± 0.21 (0.33) |
  | lag | +6.81 ± 0.58 (0.93) | +6.47 ± 0.52 (0.83) | +5.42 ± 0.55 (0.85) |
  Moving the share across its whole range changes chips by <= 0.45/h with SE 0.2-0.3, and scores move the wrong way as often as the right way.

## Decision: NO-GO
1. The gross 3-bet-pot loss is real (0.56-0.70/h) but the lever that controls it is flat within noise, so a solved chart has no demonstrated
   headroom (the sub-plan's bar is 0.15 chips/hand vs every over-folder; the controllable part is not resolvable above 0.2-0.3 SE).
2. A 50-pair gate resolves about +-0.2-0.3 chips/hand, so a chart gaining < 0.15 could not be told apart from noise: a KEEP would be a coin flip.
3. Step 2's cost is large: the 1755 x 1755 class-vs-class matrix at >= 2,000 samples is ~600x the work of the existing `eq_random`
   (which needed the generic simulator for hours), so it needs a new fast evaluator plus a discard model, on a shared laptop.
Not done: steps 2-5 (matrix, solve, `t3_preflop_chart`, gate). No tests run (no code change).

## For the manager
If the 3-bet-pot loss is wanted, it is a postflop/exploit question (why we lose -18 per 3-bet pot we call), best looked at by RD/O3 with
`lab.opps.accounting` per street on those pots, not by a chart. `PF_preflop.md` is not on `tier4/r`; it lives on `tier4/base`.
