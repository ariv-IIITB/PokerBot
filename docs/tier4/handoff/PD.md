# Handoff PD (gate P, laptop)

**Verdict: FAIL on item 2 (strict).** Per the sub-plan, **I1 ships the incumbent (`tier3x`)**; the candidate below is informational only (not uploaded). Items 1, 3, 4, 5, 7 PASS; item 6 skipped (I1 does the one final Stage 2 check).
**Branch** `claude/eloquent-snyder-5e78de` = `origin/tier4/pd`, commit bd22414 (code and report at 8a12ecd): tier4/p (PA) + p-tune (PB) + p-sel (PC) + s0 + manager docs. Report: `docs/reports/TIER4P.md` ("PD"). Runs/drivers: `logs/pd/`.
**Machine:** 14 cores, Core Ultra 5 225H, shared (load 2–21), `--processes 3`. Seeds 12000–12999, 50 pairs, light testing (no sequential extension).
**Changes to bot/:** `MEMBERS["anti_aggro"]` back to PA defaults (aa_mdf_mult 1.10, aa_bluff_mult 0.50); `hands200_<member>` stats counters in `tier4p.py`; 4 tier4p cases in `tests/test_timing_slow.py`.

| item | result |
|---|---|
| step 0 | anti_value (0.8) KEEP: chips +1.25 ± 0.30, score +0.080 ± 0.043. anti_aggro (PB values) DROP: chips −0.39 ± 0.84 → reverted to PA defaults |
| 1 offline detection | PASS: right member 0.75–0.99 of hands 200–400 vs all 7 family bots; base 1.00 vs the 5 others (24 matches each) |
| 2 member vs Tier 3 | **FAIL**: chips (locks off) +1.03 ± 0.20 / +0.61 ± 0.15 / +0.75 ± 0.17 (folder/value/aggro) pass; score (locks on) 0.560 / **0.380 ± 0.049** / 0.460, floor ≈ 0.40. anti_value re-run on fresh seeds 0.430 ± 0.050, combined 0.405 ± 0.035 (floor 0.43), still under |
| 3 vs tier3x | PASS: h2h score 0.450 ± 0.050; pool chips +1.82 ± 0.74 (z 2.5), no bot down; score +0.045 ± 0.024. Families: value +2.08 ± 0.29, aggro (lag+maniac) +2.97 ± 0.94 |
| 4 live detection | PASS: 0.83–1.00 of hands ≥ 200 by the right member (conv_opp3 0.91, rules 0.83, exploiter 0.94, lag 0.99, trapper 0.99, minraise 0.98, maniac 1.00) |
| 5 adversary | PASS: +19.49 ± 0.25 vs tier3x +19.43 ± 0.24; strict +17.18 ± 0.21 vs +16.88 ± 0.21 |
| 6 Stage 2 | skipped (I1) |
| 7 timing/size | PASS: ratio tier4p/tier3 1.01 (calling_station, 29 %) and 0.98 (trapper, 17 %); slow tier4p tests 4 passed; memory 50.5 MB; fast suite 1353 passed, 2 skipped; package passed |

## Reading the FAIL
Item 2's anti_value miss is small and the member is never played against a balanced bot like Tier 3 (it needs a valueonly/trapper posterior with ≥ 60 observations); items 3 (auto vs tier3x, incl. the head-to-head) pass. The decision is the manager's/I1's: the strict rule says ship `tier3x`; if the user overrides, ship `tier4p` with anti_value as is. Chips of tier4p vs tier3x: gains come from trapper (+1.66 ± 0.19), minraise (+0.42 ± 0.22) and maniac (+3.06); nothing vs the three strong bots (conv_opp3 −0.13 ± 0.31, exploiter −0.06 ± 0.28, rules +0.02 ± 0.28, all still losing chips). anti_folder = tier3x's own moves, adds nothing.
Extra: auto vs forced anti_folder is equal on the over-folder bots within noise (exploiter −0.92 ± 0.22 vs −0.73 ± 0.13); auto is better on trapper (+1.86 vs +0.33) and minraise.

## Candidate (informational, not for upload while FAIL)
`dist/submission.zip` (built with `--zip --stage2 --brain tier4p`, 209 KB, all checks passed), sha256 `b0902088a1bb10f16014b792f597bf16918547242bf74c07846f1eb839564b01`. `dist/` is git-ignored; rebuild with the same command.

## Cautions
- `lab.eval --locks off` leaves the opponent's lock on: locks-off scores vs tier3/tier3x are not meaningful (0.2–0.3); used chips from locks off, scores from locks on.
- The adversaries are never read as over-folders (X2: unknown), so the bail-out path is not exercised as on-then-off; stop-loss fired in 6–7 % of matches vs conv_opp3/rules/exploiter.
- tier4p's base member is Tier 3, not tier3x; I1 should merge with tier4/int baselines per the manager's note (new comparisons use tier4/int).
