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

## Stage 1: E1 (discard) and E2 (tables)

Run 2026-10-29 on a 14-core machine, 30 pairs per opponent, 7 matches at a time, from a frozen copy
of the repo (`tools/e_eval/run_batch.sh`). Chips/hand ± SE (match score in brackets for the
non-trivial opponents). Configs: **D** = Phase D (`discard_mode=pimc`, no tables); **E1f** = sampled
fast discard, no tables; **E1fT** = fast discard + embedded tables. Smart rollout discards were
already dropped earlier (+3 vs stations but −1.3 ± 0.4 vs tier1).

| | tier1 | calling_station | tight | maniac | starter | opp3 | opp4 |
|---|---|---|---|---|---|---|---|
| D | −1.00±0.41 (0.35) | +7.77±0.11 | +8.22±0.29 | +49.29±0.76 | +6.63±0.12 | −0.18±0.10 (0.43) | −1.37±0.28 (0.32) |
| E1f | −0.46±0.32 (0.42) | +7.83±0.14 | +8.58±0.36 | +51.61±0.77 | +7.11±0.12 | −0.17±0.09 (0.43) | −1.29±0.28 (0.28) |
| E1fT | +0.29±0.30 (0.55) | +8.25±0.12 | +8.60±0.36 | +54.82±0.61 | +7.54±0.14 | −0.05±0.10 (0.53) | −1.21±0.28 (0.28) |

`--compare` verdicts (diff ± SE): **E1 fast vs D**: tier1 +0.54±0.52, starter +0.48±0.17 (z 2.8),
maniac +2.32±1.08 (z 2.1), all others within noise, no opponent drops: **KEEP**. **E2 tables vs E1f**:
tier1 +0.75±0.44, calling_station +0.42±0.18 (z 2.3), starter +0.43±0.18 (z 2.3), maniac +3.21±0.98
(z 3.3), opp3 +0.12, opp4 +0.08, tight +0.02: no drops: **KEEP**. Tier 1 is the opponent that runs
the current defaults (fast discard + tables) in every column, so the tier1 column is Tier 2
(variant) vs the shipped-style bot. Offline discard quality (`lab.discard_bench`): fast beats old PIMC by
+0.007..+0.009 ± 0.003 share of pot.
