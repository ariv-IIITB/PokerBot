# RC handoff: gate R, stage 1 (the restricted river, stage 2, is NOT done)

Branch `tier4/r` (worktree `claude/rc-d4aba9`, cut from RB `aa0bbc1`, merged `origin/tier4/ra2`). Code: `aecce42` (hook + accounting), `e53aa45` (task B), final HEAD is the handoff commit.
Machine: Intel Core Ultra 5 225H, nproc 14, shared with PB/DA (every timing run under the exclusive laptop lock, 1 BLAS thread; evals nice, `--processes` 6 then 3). Python 3.11. Seeds 30000-30049, extension 30100-30149.

## Result: gate R = FAIL on one item; `t3_river_solver` stays OFF in DEFAULTS (nothing flipped, `embedded.py` untouched)
| item (50 pairs per point, flag on vs `tier3`) | number | |
|---|---|---|
| head to head, score >= 0.5 - 2 SE | 0.490 ± 0.050 (100 matches), chips -0.00 ± 0.02 | PASS |
| pool chips, locks off | sum +0.27 ± 0.50; conv_opp3 +0.43 ± 0.20 (z +2.1); no bot down | PASS |
| pool score, locks on | 0.623 -> 0.643, +0.020 ± 0.021 | PASS |
| combined river buckets > 2 SE (conv_opp3, exploiter) | +0.497 ± 0.270 (z +1.8), +0.084 ± 0.270 (z +0.3) | **FAIL** |
| timing ratio <= 1.4 (1000h, final code) | x1.328 (31 % of bank) / x1.288 (19 %), 0 hits, worst reply 25 ms | PASS |
**Extension (fresh seeds, the two deciding bots, 50 pairs):** river-all conv_opp3 -0.121 ± 0.266 (z -0.5), exploiter -0.015 ± 0.261 (z -0.1); pooled 100 pairs conv_opp3 +0.188 ± 0.189 (z +1.0), exploiter +0.035 ± 0.188 (z +0.2). The first-50 lead does not repeat.
Own-range caveat (RB): 20 % of spots move the EV > 0.20 pot depending on our assumed range.

## Plainly: what the gate tested
Gate R tests the solver at its **unloaded 2x-server behaviour** (pinned 110 passes; fire check 722 solves, 0 fallbacks). Under heavy CPU contention the shipped wall-clock box fell back to Tier 3's river on **56 %** of decisions (325 solves, 420 no-pass + 52 few-pass, median 45 passes, 2 pairs vs conv_opp3): safe, but no gain. The first (wall-clock) gate outputs are in `logs/rc/gate_walltime_invalid/`, unused.

## Built
* Hook uses RA2's `solve_river(auto=True)` on full 990/903 ranges; sampling and the 150-pass cap removed (`river_max_iters` back as lab-only, default 0). Full-range costs (laptop median ms): theirs 1.9, own range 1.3, ranks 0.45. Own range not optimised (not a bottleneck).
* **Box (shipped):** `river_box_mult` 3.9, `river_budget_s` 0.040 (was 4.0 / 0.020). 2x-clock harness (`lab/rc_ratio.py`; `lab.timing_bench` can't pass a brain config): mult 3 -> x1.19/1.21, 3.5 -> x1.27/1.29, 4 -> x1.34/1.37 (400h calling_station / trapper). The ceiling never binds; the multiplier does. Not raised further (RA2: flat above 40 ms).
* **Accounting SE:** `--report accounting` prints chips/hand ± SE over pairs per bucket plus a `river-all` line; `lab/opps/river_compare.py` compares two files (SEs in quadrature). Edited `lab/opps/track.py` and one line of `lab/eval.py` (outside the R row, additive).
* **Task A (margin, `lab/rc_margin.py`):** river decisions max 10.7 ms wall (x2: 21 ms) vs hard limit 80 ms: 0.13 (x2: 0.27) <= 0.5. No hard-limit change. One non-river spike 20.6 ms (x2 = 0.52 of 80 ms), baseline Tier 3.
* **Task B (middle rung, `bot/main.py` `choose`/`retry_cheap`):** Tier 3 at budget 0 (5,700 decisions): p99 <= 2 ms per street (cold max 12.7 / 19.6 ms), 0 illegal, 0 exceptions (`lab/rc_budget0.py`). On deadline hit or brain exception: retry once at budget 0 under 30 ms, else Tier 0; emergency -> Tier 0 directly. Counters `deadline_retries`/`retry_wins`. 3 new test groups in `tests/test_main.py`. Fast suite 1340 passed, 2 skipped (after B).
* Files outside the R row touched: `bot/main.py`, `lab/opps/track.py`, `lab/eval.py`, `tests/test_main.py`, `tests/test_eval.py`. `river_solver.py` untouched. `lab.eval` stats block reads all zeros for Tier 3 here (counters don't reach it), so pass counts come from the rc_* harnesses.

## Not done
Stage 2 (restricted river / RNR) not built: gate failed. No slow suite run (light-testing rule); `tests/test_river_timing.py` defaults now match the shipped 3.9 / 0.040 (hook test updated).

## Recommendation (mine, not a decision)
**Don't ship the flag as it stands** (no demonstrated gain: 100-pair river-all z +1.0 / +0.2; costs ~1.3x bank, ~30 % of it; mostly inert under load). Ship task B (budget-0 retry) regardless: it is independent of the flag and removes the fold-on-timeout cliff. If the user wants the solver anyway: it is safe on every other item.
Logs: `logs/rc/` (gate, ext, timing, margin), report `docs/reports/TIER4_RIVER.md` (RC section). Push: `git push origin HEAD:refs/heads/tier4/r`.
