# Tier 4P: gate X and the portfolio brain (PA)

Machine: 4 vCPU (`nproc` = 4), Intel Xeon @ 2.80GHz, `--processes 3`. All numbers below come from this one machine.

## Gate X: `tier3x` vs `tier3`
Training pool (`--pool train`, 6 discard bots), `--variant discard_holdem`, 50 pairs (100 matches) per bot,
seeds 8000–8049, two arms back to back. Raw files: `logs/pa/gx_*.txt`.

| bot | tier3 chips | tier3x chips | tier3 score | tier3x score |
|---|---|---|---|---|
| d_conv_opp3 | -1.71 ± 0.22 | -1.42 ± 0.19 | 0.400 ± 0.049 | 0.490 ± 0.050 |
| d_new_rules | -0.99 ± 0.16 | -0.75 ± 0.16 | 0.490 ± 0.050 | 0.550 ± 0.050 |
| d_new_lag | +5.47 ± 0.27 | +5.43 ± 0.27 | 0.950 ± 0.022 | 0.950 ± 0.022 |
| d_new_trapper | -0.18 ± 0.16 | -0.01 ± 0.16 | 0.660 ± 0.048 | 0.680 ± 0.047 |
| d_new_exploiter | -1.14 ± 0.19 | -1.33 ± 0.20 | 0.350 ± 0.048 | 0.360 ± 0.048 |
| d_new_minraise | -0.14 ± 0.17 | +0.22 ± 0.13 | 0.650 ± 0.048 | 0.720 ± 0.045 |
- **Chips (locks off, `lab.eval --compare`):** sum +0.83 ± 0.67 chips/hand (z +1.2); no bot down by more than 2 SE. Part 1 KEEP.
- **Match score (locks on):** mean 0.583 → 0.625, diff +0.042 ± 0.026 (z +1.6); no bot down. Part 2 KEEP.
  (`lab/opps/score_compare.py` from S0 had not landed; computed by hand from the score lines, SE per bot combined as sqrt(a²+b²), mean over 6 bots.)
- **Verdict: gate X KEEP. The incumbent is `tier3x`.** Neither part is significant on its own; it only picks the development base. I1's bar decides what ships.
- The locks-on `tier3x` arm was cut off by a worker restart after 4 bots. The other two (`d_new_exploiter`, `d_new_minraise`)
  were run afterwards on the same seeds, same machine (`gx_tier3x_on_part1/2.txt`, merged in `gx_tier3x_on.txt`).

## `tier4p`
`bot/brains/tier4p.py`: `Tier4PBrain(Tier3Brain)`; members are pure parameter overrides on `adjusted()`'s dict (`apply_member`).
`member` (default `"auto"`) forces one; auto calls `bot/brains/tier4p_select.choose_member` (stub: `"base"`).
Numbers per member are in `MEMBERS`; the `members` param holds partial overrides, e.g.
`tier4p:{"member":"anti_aggro","members":{"anti_aggro":{"aa_call_margin":-0.05}}}`.
Errors in a member or in selection fall back to Tier 3's params (`stats["p_errors"]`); `stats` has `hands_<member>` and `decisions_<member>`.

| member | what it does |
|---|---|
| base | Tier 3 unchanged |
| anti_folder | over-folder move at λ=1 (`exploit.apply_overfolder`); plus the value-only river margin when the posterior's implied river bluff share ≤ `x_vo_cut`, scaled by min(1, n/`x_vo_min_obs`) |
| anti_value | value-only margin at λ=1 (river call margin + `x_vo_margin`); fold if equity < `av_raise_fold_eq` facing a raise on a street where we had already acted (new override of `_facing_bet`; flop, turn and river) |
| anti_aggro | call_margin + `aa_call_margin` (−0.03), mdf_flop/turn × `aa_mdf_mult` (1.1, cap 1), pure bluffs × `aa_bluff_mult` (0.5), river_air_share ÷ the same |

Refactor: `exploit.adjust` now calls the new `apply_overfolder` / `apply_valueonly` (same behaviour; `tests/test_exploit.py` unchanged and green).

## Checks
- `tests/test_tier4p.py` (29) + `tests/test_exploit.py`: 43 passed.
- Fast suite: 1318 passed, 2 skipped, 1 failed: `test_tier1_beats_random_and_plays_legally` (time-based, failed under `-n auto` load; passes alone twice; not touched by this work).
- `tests/test_timing_slow.py` (`-m slow`): 10 passed.
- `lab.timing_bench`, 400 hands, ×2 slower, `calling_station`, seed 1, back to back: tier3 44 % of the bank (13.34 s used), tier4p 43 % (12.90 s); ratio 0.97 (limit 1.4). Worst decision 17.8 ms vs 24.2 ms.
- Member sanity, 8 pairs, locks off, seeds 8050+ (not a gate, `logs/pa/san_*`), chips/hand base → member:
  anti_folder: exploiter −1.02 → −0.14, conv_opp3 −2.86 → −1.47, rules −1.27 → −0.66;
  anti_value: minraise −0.31 → +0.74, trapper −0.29 → +0.77;
  anti_aggro: lag +4.88 → +5.55, maniac +46.4 → +50.1 (SEs 0.3–1.1; nothing breaks play).

## PB (laptop): member tuning

Machine: 14 cores, Intel Core Ultra 5 225H, shared with other sessions (evals at `--processes` 4 → 6 → 13 → 5, `nice -n 15`;
load average 8–31, so wall-clock-budgeted bots saw varying load: absolute chips differ between rounds, only same-seed arms are compared).
Method (README "Aim" + light testing, user 2026-11-03): coordinate descent from PA's defaults at PA's grid step, 30 pairs per point,
fresh seeds each round (centre re-run on the same seeds), locks off, chips summed over the member's family; move if the best
candidate beats the centre by z > 1 (`lab.eval` per-bot differences, SEs added in quadrature); at most 3 rounds; then a 3 × 3 grid on the
two parameters with the largest swing; then ONE 50-pair confirmation vs the PA defaults (fresh seeds 52000+, locks off = chips, locks on = score
via `lab/opps/score_compare.py`), the two-part rule; then ONE 30-pair restriction vs `tier3` (locks off, ≥ −0.10 chips/hand).
Driver `logs/pb/pb_tune.py`; every run is a file in `logs/pb/<member>/runs/`. Seeds: tuning 51000 (anti_folder) / 51300 / 51600, confirmation and
restriction 52000 / 52300 / 52600 (the restriction reuses the confirmation seeds: a different matchup).
Not done (light testing): sequential extension to 200 pairs; the confirmations are single 50-pair runs.

| member | PA defaults | final | confirmation vs defaults (50 pairs) | restriction vs tier3 (30 pairs) | decision |
|---|---|---|---|---|---|
| anti_folder | 0.60 / 2.5 / 0.12 | unchanged (no move in round 1, no grid move) | not needed | not needed | **defaults** |
| anti_value | `x_vo_margin` 0.12, `av_raise_fold_eq` 0.60 | `av_raise_fold_eq` **0.80** | chips sum +1.08 ± 0.29 (trapper +1.16 ± 0.22, minraise −0.08 ± 0.18); score 0.710 → 0.820, +0.110 ± 0.042 | +0.37 ± 0.20 /hand | **KEEP** |
| anti_aggro | −0.03 / 1.10 / 0.50 | `aa_mdf_mult` **1.0**, `aa_bluff_mult` **0.75** | chips sum +0.90 ± 0.96 (z +0.9); score 0.975 → 0.995, +0.020 ± 0.012 | +0.56 ± 0.23 /hand | **KEEP** (passes the rule, not significant) |

Cautions. anti_value's gain is almost all against the trapper (a bot that never bluffs, so folding medium hands to its raises is nearly free);
it is not significant against minraise. anti_aggro's confirmation is within noise (z +0.9 chips, +1.7 score) and the maniac score is saturated at 1.0;
the change moves the member back towards Tier 3's own values (`aa_mdf_mult` 1.0 = no MDF change; bluffs 0.75 of Tier 3's instead of 0.5).
`MEMBERS` now holds `av_raise_fold_eq` 0.80, `aa_mdf_mult` 1.00, `aa_bluff_mult` 0.75; everything else is as PA left it.

Timing (locked, ×2 slower, 400 hands, calling_station, seed 1, back to back): tier3 29 % of the bank, tier4p 29 %, forced anti_value 29 %, forced anti_aggro 29 %; ratio 1.00 (limit 1.4). Fast suite 1319 passed, 2 skipped.

The full per-point logs follow (generated by the driver).

### anti_folder: family d_new_exploiter, d_conv_opp3, d_new_rules; defaults x_bluff_max=0.6, x_river_bluff_mult=2.5, x_vo_margin=0.12

#### Descent round 1 (seeds 51000-51029, 30 pairs, locks off)
centre x_bluff_max=0.6, x_river_bluff_mult=2.5, x_vo_margin=0.12: d_new_exploiter -0.75±0.21, d_conv_opp3 -1.07±0.31, d_new_rules -0.28±0.20 | sum -2.10
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| x_bluff_max | 0.45 | -1.04 ± 0.60 | -1.7 |
| x_bluff_max | 0.75 | +0.00 ± 0.60 | +0.0 |
| x_river_bluff_mult | 1.5 | -0.83 ± 0.63 | -1.3 |
| x_river_bluff_mult | 3.5 | -0.58 ± 0.60 | -1.0 |
| x_vo_margin | 0.06 | -0.23 ± 0.58 | -0.4 |
| x_vo_margin | 0.18 | -0.25 ± 0.60 | -0.4 |
**no move**: best candidate x_bluff_max=0.75 diff +0.00, z +0.0 <= 1

#### Grid on x_bluff_max, x_river_bluff_mult around x_bluff_max=0.6, x_river_bluff_mult=2.5, x_vo_margin=0.12 (swings x_bluff_max 1.04, x_river_bluff_mult 0.83, x_vo_margin 0.25; seeds 51100-51129)
| x_bluff_max \ x_river_bluff_mult | 1.5 | 2.5 | 3.5 |
|---|---|---|---|
| 0.45 | -0.69 ± 0.69 (z -1.0) | -0.65 ± 0.64 (z -1.0) | -0.55 ± 0.63 (z -0.9) |
| 0.6 | -0.94 ± 0.67 (z -1.4) | centre | -0.90 ± 0.64 (z -1.4) |
| 0.75 | -0.47 ± 0.67 (z -0.7) | -0.65 ± 0.64 (z -1.0) | -0.66 ± 0.65 (z -1.0) |
**no grid move** (best other point diff +0.00, z +0.0 <= 1)

Final point: x_bluff_max=0.6, x_river_bluff_mult=2.5, x_vo_margin=0.12 (defaults x_bluff_max=0.6, x_river_bluff_mult=2.5, x_vo_margin=0.12)

Final point = PA defaults: nothing to confirm; MEMBERS unchanged.
VERDICT: defaults

### anti_value: family d_new_minraise, d_new_trapper; defaults x_vo_margin=0.12, av_raise_fold_eq=0.6

#### Descent round 1 (seeds 51300-51329, 30 pairs, locks off)
centre x_vo_margin=0.12, av_raise_fold_eq=0.6: d_new_minraise +0.58±0.16, d_new_trapper +0.77±0.19 | sum +1.35
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| x_vo_margin | 0.06 | +0.01 ± 0.36 | +0.0 |
| x_vo_margin | 0.18 | +0.03 ± 0.38 | +0.1 |
| av_raise_fold_eq | 0.5 | -0.38 ± 0.34 | -1.1 |
| av_raise_fold_eq | 0.7 | +0.56 ± 0.36 | +1.6 |
**move** av_raise_fold_eq -> 0.7 (diff +0.56, z +1.6)

#### Descent round 2 (seeds 51330-51359, 30 pairs, locks off)
centre x_vo_margin=0.12, av_raise_fold_eq=0.7: d_new_minraise +0.62±0.15, d_new_trapper +1.38±0.21 | sum +2.00
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| x_vo_margin | 0.06 | -0.07 ± 0.36 | -0.2 |
| x_vo_margin | 0.18 | -0.07 ± 0.38 | -0.2 |
| av_raise_fold_eq | 0.6 | -0.48 ± 0.37 | -1.3 |
| av_raise_fold_eq | 0.8 | +0.68 ± 0.38 | +1.8 |
**move** av_raise_fold_eq -> 0.8 (diff +0.68, z +1.8)

#### Descent round 3 (seeds 51360-51389, 30 pairs, locks off)
centre x_vo_margin=0.12, av_raise_fold_eq=0.8: d_new_minraise +0.38±0.15, d_new_trapper +1.98±0.24 | sum +2.36
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| x_vo_margin | 0.06 | -0.27 ± 0.40 | -0.7 |
| x_vo_margin | 0.18 | -0.40 ± 0.41 | -1.0 |
| av_raise_fold_eq | 0.7 | -0.55 ± 0.38 | -1.5 |
| av_raise_fold_eq | 0.9 | +0.12 ± 0.37 | +0.3 |
**no move**: best candidate av_raise_fold_eq=0.9 diff +0.12, z +0.3 <= 1

#### Grid on av_raise_fold_eq, x_vo_margin around x_vo_margin=0.12, av_raise_fold_eq=0.8 (swings x_vo_margin 0.40, av_raise_fold_eq 0.68; seeds 51400-51429)
| av_raise_fold_eq \ x_vo_margin | 0.06 | 0.12 | 0.18 |
|---|---|---|---|
| 0.7 | -0.86 ± 0.36 (z -2.4) | -0.58 ± 0.33 (z -1.8) | -0.44 ± 0.34 (z -1.3) |
| 0.8 | +0.07 ± 0.35 (z +0.2) | centre | +0.18 ± 0.36 (z +0.5) |
| 0.9 | +0.05 ± 0.37 (z +0.1) | +0.19 ± 0.37 (z +0.5) | +0.21 ± 0.37 (z +0.6) |
**no grid move** (best other point diff +0.21, z +0.6 <= 1)

Final point: x_vo_margin=0.12, av_raise_fold_eq=0.8 (defaults x_vo_margin=0.12, av_raise_fold_eq=0.6)

#### Confirmation vs defaults, 50 pairs, seeds 52300-52349, locks off (chips)
```
d_new_minraise +0.62 -> +0.54  diff -0.08 ± 0.18 (z -0.4)
d_new_trapper +0.70 -> +1.86  diff +1.16 ± 0.22 (z +5.3)  improved
sum      diff +1.08 ± 0.29 (z +3.8)
verdict: KEEP
```
locks on (score):
```
d_new_minraise   0.680 -> 0.740  diff +0.060 ± 0.064
d_new_trapper    0.740 -> 0.900  diff +0.160 ± 0.053
overall          0.710 -> 0.820  diff +0.110 ± 0.042 (z +2.6, 2 bots)
verdict: KEEP-score
```
Two-part rule: chips pass (sum +1.08 ± 0.29), score pass -> KEEP

#### Restriction vs tier3, 30 pairs, locks off: +0.37 ± 0.20 chips/hand (ok, limit -0.10); match score 0.167 ± 0.049 (info)
VERDICT: KEEP {"x_vo_margin": 0.12, "av_raise_fold_eq": 0.8}

### anti_aggro: family d_new_lag, maniac; defaults aa_call_margin=-0.03, aa_mdf_mult=1.1, aa_bluff_mult=0.5

#### Descent round 1 (seeds 51600-51629, 30 pairs, locks off)
centre aa_call_margin=-0.03, aa_mdf_mult=1.1, aa_bluff_mult=0.5: d_new_lag +4.61±0.42, maniac +51.51±0.91 | sum +56.12
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| aa_call_margin | -0.06 | +1.78 ± 1.30 | +1.4 |
| aa_call_margin | 0 | -1.80 ± 1.24 | -1.4 |
| aa_mdf_mult | 1 | +1.96 ± 1.29 | +1.5 |
| aa_mdf_mult | 1.2 | +0.43 ± 1.29 | +0.3 |
| aa_bluff_mult | 0.25 | +0.40 ± 1.26 | +0.3 |
| aa_bluff_mult | 0.75 | +0.06 ± 1.29 | +0.0 |
**move** aa_mdf_mult -> 1 (diff +1.96, z +1.5)

#### Descent round 2 (seeds 51630-51659, 30 pairs, locks off)
centre aa_call_margin=-0.03, aa_mdf_mult=1, aa_bluff_mult=0.5: d_new_lag +5.22±0.49, maniac +53.30±0.85 | sum +58.52
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| aa_call_margin | -0.06 | -0.74 ± 1.34 | -0.6 |
| aa_call_margin | 0 | -3.35 ± 1.24 | -2.7 |
| aa_mdf_mult | 0.9 | -1.53 ± 1.25 | -1.2 |
| aa_mdf_mult | 1.1 | -0.51 ± 1.35 | -0.4 |
| aa_bluff_mult | 0.25 | -1.45 ± 1.26 | -1.1 |
| aa_bluff_mult | 0.75 | +2.13 ± 1.38 | +1.5 |
**move** aa_bluff_mult -> 0.75 (diff +2.13, z +1.5)

#### Descent round 3 (seeds 51660-51689, 30 pairs, locks off)
centre aa_call_margin=-0.03, aa_mdf_mult=1, aa_bluff_mult=0.75: d_new_lag +5.63±0.59, maniac +52.64±0.68 | sum +58.27
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| aa_call_margin | -0.06 | -0.67 ± 1.30 | -0.5 |
| aa_call_margin | 0 | -2.76 ± 1.15 | -2.4 |
| aa_mdf_mult | 0.9 | -1.04 ± 1.39 | -0.7 |
| aa_mdf_mult | 1.1 | -0.91 ± 1.28 | -0.7 |
| aa_bluff_mult | 0.5 | -1.50 ± 1.26 | -1.2 |
| aa_bluff_mult | 1 | +0.37 ± 1.38 | +0.3 |
**no move**: best candidate aa_bluff_mult=1 diff +0.37, z +0.3 <= 1

#### Grid on aa_call_margin, aa_bluff_mult around aa_call_margin=-0.03, aa_mdf_mult=1, aa_bluff_mult=0.75 (swings aa_call_margin 3.35, aa_mdf_mult 1.96, aa_bluff_mult 2.13; seeds 51700-51729)
| aa_call_margin \ aa_bluff_mult | 0.5 | 0.75 | 1 |
|---|---|---|---|
| -0.06 | -0.35 ± 1.21 (z -0.3) | +0.07 ± 1.24 (z +0.1) | -0.14 ± 1.25 (z -0.1) |
| -0.03 | -1.72 ± 1.25 (z -1.4) | centre | -1.07 ± 1.22 (z -0.9) |
| 0 | -2.54 ± 1.11 (z -2.3) | -2.50 ± 1.14 (z -2.2) | -4.01 ± 1.25 (z -3.2) |
**no grid move** (best other point diff +0.07, z +0.1 <= 1)

Final point: aa_call_margin=-0.03, aa_mdf_mult=1, aa_bluff_mult=0.75 (defaults aa_call_margin=-0.03, aa_mdf_mult=1.1, aa_bluff_mult=0.5)

#### Confirmation vs defaults, 50 pairs, seeds 52600-52649, locks off (chips)
```
d_new_lag +5.17 -> +5.76  diff +0.59 ± 0.54 (z +1.1)
maniac   +51.65 -> +51.96  diff +0.31 ± 0.79 (z +0.4)
sum      diff +0.90 ± 0.96 (z +0.9)
verdict: KEEP
```
locks on (score):
```
d_new_lag        0.950 -> 0.990  diff +0.040 ± 0.024
maniac           1.000 -> 1.000  diff +0.000 ± 0.000
overall          0.975 -> 0.995  diff +0.020 ± 0.012 (z +1.7, 2 bots)
verdict: KEEP-score
```
Two-part rule: chips pass (sum +0.90 ± 0.96), score pass -> KEEP

#### Restriction vs tier3, 30 pairs, locks off: +0.56 ± 0.23 chips/hand (ok, limit -0.10); match score 0.183 ± 0.050 (info)
VERDICT: KEEP {"aa_call_margin": -0.03, "aa_mdf_mult": 1.0, "aa_bluff_mult": 0.75}

## PD (laptop): gate P, light testing

Machine: 14 cores, Intel Core Ultra 5 225H, shared with other sessions (load 2–21), `--processes 3`, `nice -n 15`, shared `flock` for evals, exclusive for timing.
Branch `claude/eloquent-snyder-5e78de` = `origin/tier4/pd`: `tier4/p` (PA) + `tier4/p-tune` (PB) + `tier4/p-sel` (PC) + `tier4/s0`. Seeds 12000–12999, 50 pairs per comparison (light testing: no sequential extension, item 6 skipped, I1 does the one Stage 2 check).
Drivers and every run file: `logs/pd/` (`pd_gate.py`, `analyze.py`, `replay_detect.py`, `runs/`). Both arms always back to back.

**Note on locks-off runs:** `lab.eval --locks off` switches the endgame lock off for our brain only; an opponent `tier3`/`tier3x` keeps its lock. So match scores of locks-off head-to-heads vs a Tier 3 brain are not meaningful (0.2–0.3); chips come from locks off, scores from locks on.

### Step 0: PB's values binding (fresh seeds 12000 / 12100, vs PA defaults)
- `anti_value` (av_raise_fold_eq 0.8): chips +1.25 ± 0.30 (minraise +0.01 ± 0.19, trapper +1.24 ± 0.23), score 0.705 → 0.785 (+0.080 ± 0.043). **KEEP.**
- `anti_aggro` (mdf 1.0, bluff 0.75): chips −0.39 ± 0.84 (lag +0.43, maniac −0.82), score −0.010 ± 0.018. **DROP: MEMBERS back to PA defaults** (aa_mdf_mult 1.10, aa_bluff_mult 0.50). All later runs use the reverted values.
- `anti_folder`: defaults (PB found no better point).

### Gate P
1. **Detection, offline (PASS).** S0 recordings, seeds 9000–9011, real selection code replayed decision by decision, 24 matches per bot, share of hands 200–400 by the right member: exploiter 0.85, conv_opp3 0.83, rules 0.75, minraise 0.90, trapper 0.75, lag 0.94, maniac 0.99; base 1.00 vs starter, calling_station, tight, random_legal, all_in (need 0.70; 0.90 for random_legal / all_in). In 1–7 of 24 matches per family bot the member never switched on (the mean passes). `logs/pd/item1.txt`.
2. **Each forced member vs Tier 3 (FAIL, anti_value score).** 50 pairs. Chips, locks off: anti_folder +1.03 ± 0.20, anti_value +0.61 ± 0.15, anti_aggro +0.75 ± 0.17 (all ≥ −0.10). Match score, locks on (floor 0.5 − 2 SE ≈ 0.40): anti_folder 0.560 ± 0.050 ok, anti_aggro 0.460 ± 0.050 ok, **anti_value 0.380 ± 0.049 (< 0.402)**. A fresh-seed re-run (seeds 12250, information only): 0.430 ± 0.050; the two together 0.405 ± 0.035 (floor 0.43), still below. Locks-on chips are about −0.03 / 0.00 (the locks end the matches early).
3. **vs the incumbent tier3x (PASS).** Head-to-head, auto tier4p, 50 pairs: score 0.450 ± 0.050 (locks on, floor 0.40); chips +0.93 ± 0.18 (locks off; tier3x keeps its lock). Training pool, 50 pairs per bot, same seeds: chips (locks off) sum +1.82 ± 0.74 (z +2.5), no bot down (lag −0.09 ± 0.46, conv_opp3 −0.13 ± 0.31, rules +0.02 ± 0.28, exploiter −0.06 ± 0.28, minraise +0.42 ± 0.22, trapper +1.66 ± 0.19); score (locks on) 0.673 → 0.718, +0.045 ± 0.024, no bot down by 2 SE. **Two-part KEEP.** Families that differ from tier3x: anti_value (minraise + trapper) +2.08 ± 0.29, up by > 2 SE; anti_aggro (lag + maniac, maniac run outside the pool) +2.97 ± 0.94 (lag −0.09, maniac +3.06 ± 0.9), up by > 2 SE. anti_folder = tier3x's own moves (family −0.17 ± 0.51, not required).
4. **Live detection (PASS).** Locks-off pool runs, share of hands ≥ 200 by the right member: conv_opp3 0.91, rules 0.83 (anti_value 0.00), lag 0.99, trapper 0.99, exploiter 0.94, minraise 0.98, maniac 1.00. Stop-loss fired in 6/6/7/7 of 100 matches vs conv_opp3 / rules / exploiter (resp. lag 1, trapper 1, minraise 2); `p_errors` 0.
5. **Adversary (PASS).** 50 pairs, locks off: adversary tier4p +19.49 ± 0.25 vs tier3x +19.43 ± 0.24; adversary_strict +17.18 ± 0.21 vs +16.88 ± 0.21; score 1.000 for both. Neither adversary is ever read as an over-folder (base 100 %; strict: 101 CUSUM alarms, no switch), so this only shows the selection does not misfire on them.
6. **Stage 2: skipped** (user instruction, I1 runs the one final Stage 2 check).
7. **Timing, memory, size (PASS).** `lab.timing_bench`, 400 hands, ×2 slower, seed 1, no `--lock`, alternating tier3 / tier4p / tier3 / tier4p under the exclusive lock: vs calling_station tier3 8.66 s (29 %) / 8.66 s, tier4p 8.76 s / 8.76 s (29 %), ratio 1.01; vs d_new_trapper tier3 5.35 s / 5.25 s (17–18 %), tier4p 5.23 s / 5.16 s (17 %), ratio 0.98. Limit 1.4. `tests/test_timing_slow.py` gained 4 tier4p cases (400/60 and 1000/150 vs calling_station and d_new_trapper): 4 passed. `lab.memory_check`: 50.5 MB (limit 500). Fast suite: 1353 passed, 2 skipped. `tools.package_submission --zip --stage2 --brain tier4p`: all checks passed.

### Extra: auto tier4p vs forced anti_folder, and the strong bots
Locks off, 50 pairs, same seeds, auto vs forced `anti_folder`: exploiter −0.92 ± 0.22 vs −0.73 ± 0.13; conv_opp3 −1.59 ± 0.24 vs −1.73 ± 0.24; rules −0.58 ± 0.22 vs −0.36 ± 0.16; lag +5.96 vs +5.80; trapper +1.86 ± 0.14 vs +0.33 ± 0.13; minraise +0.73 vs +0.44. On the over-folder family forced and auto are the same within noise; auto's gain is the other families.
Auto tier4p vs tier3x on the three strong bots (chips locks off / score locks on): conv_opp3 −0.13 ± 0.31 / +0.03 ± 0.07, exploiter −0.06 ± 0.28 / −0.06 ± 0.07, rules +0.02 ± 0.28 / +0.06 ± 0.07. No gain, and we still lose chips to all three (−0.6 to −1.6 /hand in every arm).
