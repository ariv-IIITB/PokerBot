# RD handoff: river leaks, own/opponent range, exploit layer (RNR), timing

Branch `tier4/rd` (worktree `claude/rd-16d183`, merged `origin/tier4/int`). Machine: Intel Core Ultra 5 225H, nproc 14, shared; evals nice 15, `--processes 3`, timing under the exclusive lock (turnstile). Python 3.11.
Full write-up: `docs/reports/TIER4_RIVER.md`, section "RD".

## Decision: `t3_river_solver` stays OFF (nothing flipped in DEFAULTS, `embedded.py` untouched)
Failing item: **timing, 400h d_new_trapper x1.408 > 1.4** (others x1.32-1.35; 1000h x1.04-1.35). More fundamentally: **no measurable gain over Tier 3**.

## Leaks found
* Default own-range model was worse than a flat range -> fitted `OWN_BET` table (16,390 hands, held-out better). `river_own_fit` default True (affects only solver-on play).
* Opponent range sharpness refit to (beta 6, gamma 0.6). Trapper-type bots want gamma ~ 0 (adaptive gamma NOT built).
* Neither moved results: the solver's deficit is not range accuracy.

## Changes (all adaptive; no bot names/constants; inert under thin evidence)
* `t3_river_rnr`: soft best response to the observed river fold rate, mix weight pmax 0.5 · n/(n+40), min n 20. `t3_river_narrow`: range narrowed by bet-size rank (O3's idea). `t3_river_shifts`: X1/X2 shifts. All default False.
* `bot/strategy/own_range.py` (fitted `OwnInference`), `river_solver.py` (`locked_values`, `fold_obs`), `tier3.py` (new params), tests `tests/test_river_rd.py`.
* Outside my row: `bot/opponent.py` `range_weights(..., model=None)` (one optional arg); `lab/rc_ratio.py`, `lab/rc_margin.py` got `--extra` JSON. Did not touch `exploit.py`, `bot/cfr/`.

## Numbers (50 pairs, fresh seeds 70300-70349; NA = solver 110 passes + narrow + RNR + shifts; baseline pre-DA `tier3`)
* Pool chips, locks off, 5 non-blind bots: sum **+0.42 ± 0.48** (conv_opp3 -1.26 -> -1.45, exploiter +5.75 -> +6.10, lag +2.97 -> +3.07, trapper -1.33 -> -1.13, minraise +0.35 -> +0.31). PASS but no gain.
* Pool match score, locks on: 0.632 -> 0.618. conv_opp3 0.16 -> 0.10, trapper 0.37 -> 0.33 (both <0.5 with or without). PASS (within 2 SE).
* Head to head vs Tier 3, locks on, seeds 70400: **0.540 ± 0.050** (100 matches), chips +0.02 ± 0.02. PASS.
* Blind `d_new_rules`, run once (seeds 70500, locks off): **-0.74 ± 0.15**, score 0.32 (Tier 3 baseline -1.52 from an older run, not paired).
* Earlier 30-pair screens: solver alone / +shifts / +RNR / +narrow each -0.5..-1.3 summed vs Tier 3 (noise); shifts alone hurt.
* Timing (2x clock, shipped box 40 ms x3.9, NA on): 1000h x1.346 / x1.303 / x1.040 (station / trapper / conv_opp3); 400h x1.338 / **x1.408** / x1.320; 0 deadline hits, worst reply 27 ms.
* River decisions max wall 11.2 ms = 0.14 of the 80 ms hard limit (x2 0.28) <= 0.5.
* Not done: 100-pair confirmation (50 pairs only; there was no effect to confirm), graceful-under-load re-test (RC measured 56% fallbacks under heavy contention; unchanged), RD arms vs the new `tier4/int` tier3.json baseline (compared against the pre-DA `tier3`).
* Fast suite: 1346 passed, 2 skipped.

Commit: the handoff commit on `tier4/rd`.
