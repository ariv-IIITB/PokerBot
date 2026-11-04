# Handoff PA (gate X + tier4p members)

**Branch** `claude/tier4-pa-subplan-cwh07j` (from `origin/tier4/base`; the README calls it `tier4/p`). Report: `docs/reports/TIER4P.md`.
**Machine:** 4 vCPU, Xeon @ 2.80GHz, `--processes 3`.

## Gate X: KEEP, incumbent = `tier3x`
Training pool, discard_holdem, 50 pairs, seeds 8000–8049, arms back to back.
- Chips (locks off): sum +0.83 ± 0.67 /hand (z +1.2), no bot down > 2 SE.
- Match score (locks on): mean 0.583 → 0.625, +0.042 ± 0.026 (z +1.6), no bot down. (S0's score script was not there; done by hand.)
- Neither is significant alone; the gate only picks the dev base. The locks-on tier3x arm was restarted for its last 2 bots (same seeds, same machine).

## What exists
- `bot/brains/tier4p.py` (`Tier4PBrain`, `MEMBERS`, `apply_member`), `bot/brains/tier4p_select.py` (stub: `choose_member(brain, street)` -> "base"; PC fills it in, don't touch tier4p.py).
- Registered in `bot/main.py`, in `LOCK_BRAINS`; `exploit.py` gained `apply_overfolder`/`apply_valueonly` (behaviour unchanged).
- Force a member: `tier4p:{"member":"anti_folder"}`; override numbers: `"members":{"anti_folder":{"x_bluff_max":0.75}}` (partial dicts merge).
- `member:"base"` has Tier 3's params exactly (test). `stats`: `hands_<m>`, `decisions_<m>`, `p_errors`, `p_raise_folds`.
- Tests: 29 in `tests/test_tier4p.py`; fast suite 1318 passed, 2 skipped, 1 time-based flake in `test_tier1` (passes alone); slow timing 10 passed.
- Timing: tier4p 43 % vs tier3 44 % of the bank at ×2 (ratio 0.97 ≤ 1.4).
- Sanity (8 pairs, not a gate): every forced member ≥ base on its family's bots; nothing broken.

## For PB: parameters to tune (≤ 3 per member, 3 values each)
| member | parameter | default | grid |
|---|---|---|---|
| anti_folder | `x_bluff_max` | 0.60 | 0.45, 0.60, 0.75 |
| | `x_river_bluff_mult` | 2.5 | 1.5, 2.5, 3.5 |
| | `x_vo_margin` | 0.12 | 0.06, 0.12, 0.18 |
| anti_value | `x_vo_margin` | 0.12 | 0.06, 0.12, 0.18 |
| | `av_raise_fold_eq` | 0.60 | 0.45, 0.55, 0.65 (0 = off) |
| | (a third is not needed) | | |
| anti_aggro | `aa_call_margin` | −0.03 | −0.06, −0.03, 0 |
| | `aa_mdf_mult` | 1.10 | 1.0, 1.1, 1.2 |
| | `aa_bluff_mult` | 0.50 | 0.25, 0.50, 0.75 |
`x_vo_cut` (0.10) and `x_vo_min_obs` (60) are the selection conditions, not tuning knobs. Families: anti_folder vs exploiter, conv_opp3, rules;
anti_value vs minraise, trapper; anti_aggro vs lag, maniac. A single eval of 50 pairs on one bot takes ~10 min on this machine at 3 processes, so budget accordingly.

## Next
PB tunes with the grids above; PC implements `choose_member` (reads `brain.opponent.types/traits`); both branch from this one.
Decision for PD/I1: development base is `tier3x`; `tier4p`'s members are on top of Tier 3 (base member = Tier 3, not tier3x), so I1 compares them with `tier3x`.
