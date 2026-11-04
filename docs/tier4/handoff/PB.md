# Handoff PB (laptop): tune `tier4p`'s members

**Branch** `claude/p-tune-7f2c48` = `origin/tier4/p-tune` (from `tier4/p` = PA `423503e`). Report: `docs/reports/TIER4P.md` ("PB (laptop)", every point and move).
**Machine:** 14 cores, Intel Core Ultra 5 225H; shared with other sessions, `nice -n 15`, `--processes` 4 → 6 → 13 → 5, load 8–31.

## Method (light testing, README "Aim")
Coordinate descent from PA's defaults at PA's step, 30 pairs/point, fresh seeds each round (centre re-run), locks off, chips summed over the family,
move if z > 1, ≤ 3 rounds; 3 × 3 grid on the two most sensitive parameters; one 50-pair confirmation vs PA defaults (locks off chips, locks on score,
README rule 5); one 30-pair restriction vs tier3 (locks off, ≥ −0.10). No sequential extension. Seeds 51000/51300/51600 (tuning), 52000/52300/52600 (confirm, restriction).
Driver `logs/pb/pb_tune.py` (resumable), runs in `logs/pb/<member>/runs/`.

## Final values (`MEMBERS` in `bot/brains/tier4p.py`, values only)
| member | final | vs PA defaults (50 pairs, fresh seeds) | vs tier3 (30 pairs) | decision |
|---|---|---|---|---|
| anti_folder | defaults: x_bluff_max 0.60, x_river_bluff_mult 2.5, x_vo_margin 0.12 | none beat the centre by > 1 SE (round 1; grid z ≤ 0) | — | **defaults** |
| anti_value | x_vo_margin 0.12, **av_raise_fold_eq 0.80** (was 0.60) | chips +1.08 ± 0.29 /hand (trapper +1.16 ± 0.22, minraise −0.08 ± 0.18); score 0.710 → 0.820 (+0.110 ± 0.042) | +0.37 ± 0.20 /hand | **KEEP** |
| anti_aggro | aa_call_margin −0.03, **aa_mdf_mult 1.0** (was 1.10), **aa_bluff_mult 0.75** (was 0.50) | chips +0.90 ± 0.96 (z +0.9); score 0.975 → 0.995 (+0.020 ± 0.012) | +0.56 ± 0.23 /hand | **KEEP** (rule passed, not significant) |

anti_value used all 3 rounds (0.60 → 0.70 → 0.80, last round no move; grid no move). anti_aggro: mdf 1.10 → 1.0 (z +1.5), bluff 0.50 → 0.75 (z +1.5), round 3 no move, grid no move.

## Cautions for PD / I1
- anti_value's gain is almost all vs the trapper (never bluffs, so folding medium hands to its raises is nearly free); minraise unchanged. Re-check it at PD's step 0 and on I1's pool.
- anti_aggro is within noise (chips z +0.9, score z +1.7); it mostly moves the member back towards Tier 3's values. PD's step 0 can drop it to PA's defaults without loss of anything else.
- Evals ran under varying machine load (wall-clock budgets): only same-seed arms are compared; do not compare absolute chips between rounds.
- `bot/embedded.py` regenerates identically (MEMBERS is not embedded); only 3 values in `tier4p.py` changed, so PC's merge should be clean.

## Checks
- `lab.timing_bench`, 400 hands, ×2 slower, `calling_station`, seed 1, locked, back to back (this laptop): tier3 29 % of the bank (8.72 s), tier4p 29 % (8.76 s), forced anti_value 29 % (8.73 s), forced anti_aggro 29 % (8.71 s). Ratio 1.00 (limit 1.4). (A first run with the endgame `--lock` flag read 6 % for both; not comparable to PA's, discarded.)
- Fast suite `-n 4`: 1319 passed, 2 skipped. `tests/test_tier4p.py` line 89 hard-coded the old `aa_bluff_mult` 0.5; it now reads `MEMBERS` (the only test change). Slow suite not run (light testing).
