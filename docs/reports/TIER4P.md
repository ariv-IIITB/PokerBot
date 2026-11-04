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
