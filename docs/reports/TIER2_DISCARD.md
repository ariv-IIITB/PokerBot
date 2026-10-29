# Tier 2 on Discard Hold'em: Phase E results

Every step below is measured and recorded here, kept or dropped. Method (the plan's keep rule):
`lab.eval tier2:<config> --pool <pool> --pairs <n> --locks off --variant discard_holdem`, then
`--compare BEFORE AFTER`: keep a change only if the pool aggregate improves and no opponent
drops by more than 2 SE. Numbers are chips per hand ± SE over duplicate pairs (400 hands, 60 s
bank, real wall-clock budgets), so a run depends a little on machine load: before/after runs are
always played at the same time on the same machine.

Baseline "D" = the Phase D bot (`discard_mode=pimc`, random-discard rollouts, no tables, no
bluff-catch rule), reproduced by config on the current code.

## Method notes and deviations

- Evaluation pool for the step decisions: tier1, calling_station, tight, maniac, starter, opp3,
  opp4 ("core", 7 opponents) at 30 pairs, not the plan's 12 opponents at 50 pairs: Tier 2 plays
  ~22 hands/s per core here, so 50 pairs × 12 opponents would take ~1.5 h per configuration.
  random_legal and all_in carry no information (Tier 2 wins them by a wide margin whatever it
  does), opp1/opp2 are Hold'em bots on a makeshift adapter. The final check (E7) uses the full pool
  at 50 pairs.
