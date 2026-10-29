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

## Results (core pool, 30 pairs, chips/hand ± SE; match score in brackets where shown)

E1 (fast sampled discard) and E2 (embedded tables) were decided in an earlier session on the same
keep rule and are the defaults: **kept**. Smart rollouts: dropped (lose ~1.3 ± 0.4 vs tier1).
Stage 2, each config against the kept base ("base" = current defaults), same machine, run one after another:

| | tier1 | calling_station | tight | maniac | starter | opp3 | opp4 | decision |
|---|---|---|---|---|---|---|---|---|
| base | −0.06±0.27 (.53) | +8.54±0.12 | +8.60±0.33 | +53.70±0.68 | +7.44±0.13 | −0.08±0.10 (.46) | −1.35±0.33 (.33) | |
| E4 `river_bluff_slope` 0.5 | +0.08±0.38 (.48) | +8.41±0.11 | +8.40±0.32 | +53.89±0.53 | +7.49±0.11 | +0.01±0.11 (.65) | −0.65±0.23 (.42) | **kept**: no drop > 2 SE, opp3/opp4 up |
| E5 `ev_sizing` | −0.67±0.26 (.40) | +9.67±0.18 | +6.68±0.30 | +53.68±0.57 | +8.66±0.16 | −0.19±0.13 | −1.26±0.32 | dropped: −1.9 vs tight (~4 SE) |
| E6 `leftover_frac` 0.25 | −0.06±0.27 (.50) | +8.43±0.12 | +8.54±0.31 | +52.46±0.66 | +7.44±0.14 | −0.09±0.12 | −1.25±0.29 | dropped: no gain |
| `table_range_weight` 0.5 | −0.16±0.32 (.53) | +8.39±0.14 | +8.49±0.33 | +50.86±0.67 | +7.55±0.15 | −0.18±0.09 | −1.37±0.27 | dropped: −2.8 vs maniac (~3 SE) |

E4's gain is marginal (opp4 +0.7 ± 0.4); kept because the rule allows it and it targets the known river leak.
Note: the E4 change was measured with 30 pairs only; E7 re-checks it on the full pool at 50 pairs.
