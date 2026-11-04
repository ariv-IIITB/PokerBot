# RF handoff: why the CFR river lost chips, and a fixed solver variant (D4)

Branch `tier4/rf` (on `origin/tier4/int` e50bc3a+later merges). Intel Core Ultra 5 225H, nproc 14, shared; evals nice 15, `--processes 3`, timing under the exclusive lock. Seeds 73000-73149. Logs `logs/rf/`, tools `lab/rf_spots.py` (river chips per spot class), `lab/rf_cov.py`.
BASE = `tier3x:{"x_narrow":true,"x_air_eq":0.45}` (= tier4/int, solver flag off). 30 pairs, locks off, sums over conv_opp3/exploiter/trapper.

## Diagnosis (25 pairs/bot; river chips per hand by class of our first river decision, solver minus BASE)
* (a) conv_opp3 solver: first +0.72, checked_to -0.03, face_small -0.15, **face_big -0.97**. exploiter: first -0.73, face_big -0.62. trapper: first -1.45, checked_to -0.70, face_big -0.51. It loses facing bets (calls 51-64% vs BASE 7-16%) and as first actor vs callers/over-folders (bets 19-29% vs BASE 36-51%).
* (b) Narrowing is far too weak: top-30% hands carry 0.46 -> 0.58 of the range for every bet size (barely size-dependent) while real showdown bettors are 0.69-0.92 top-30% (conv) and 0.9-1.0 (exploiter, trapper). Cause: the blend alpha = n/(n+narrow_n0=30) on top of already prior-shrunk f and b.
* (c) RNR weight at match end 0.22-0.31 (max ~0.35): small. Model fold rate is shrunk toward the prior: real vs model 0.72-0.78 vs 0.65-0.71 (exploiter, conv), 0.25-0.36 vs 0.29-0.38 (trapper). Bias is small, the weight is the issue.
* (d) face_big class costs 0.5-1.0 chips/hand per bot, about half of the total river deficit (-0.4 .. -2.8). After `narrow_n0 0.001` face_big is -0.35 (conv), 0.00 (exploiter), -0.05 (trapper).
* (e) own-range sensitivity with the fitted OwnInference (200 spots): mean |dEV| 0.053 pot, only 6 % of spots > 0.20 pot (RB: 20 % with the old model). Not a weak point.
* After the n0 fix the remaining loss is vs the trapper as first actor: the equilibrium bets by hand percentile 0.6-0.8 only 35 % (BASE 77 %), top 20 % 69 % (BASE 99 %), and bluffs 31 % of the bottom 20 % (BASE 5 %). Fix: RNR vs callers.

## Changes (all default OFF; adaptive; no bot names)
* `narrow_n0` (existing param) 30 -> 0.001 in the arm: no second shrink of the narrowed range. `rnr_dir` (new, -1 = best response only when the observed river fold rate is below the equilibrium one, i.e. a caller; 0 = both). `river_face_base` (new, facing a bet Tier 3 decides) - tested, not needed.
* Tests: `tests/test_river_rd.py` (+1). Fast suite 1351 passed, 2 skipped.

## Candidates (30 pairs, diff vs BASE, conv / exploiter / trapper, sum +- SE)
C1 narrow n0 + RD's rnr+shifts: +0.45 / -0.45 / -0.36, -0.36 +- 0.46. C2 C1 + rnr pmax .9 n0 10 min_n 10: +0.49 / **-1.52** / +0.01, -1.02. (RD's NA: -2.29 +- 0.45.)
D1 solver + narrow(n0 0.001) only: +0.68 / -0.03 / -0.67, -0.02 +- 0.42. D2 D1 + river_face_base: +0.31 / 0.00 / -0.53, -0.22. D3 D2 + rnr/shifts: +0.42 / 0.00 / -0.38, +0.04.
**D4 = D1 + rnr (pmax .9, n0 10, min_n 10, rnr_dir -1), no shifts: +0.34 / -0.24 / +0.18, +0.28 +- 0.42.** Strong two-sided RNR and shifts hurt (exploiter punishes it).

## D4 confirmation: 50 pairs, seeds 73100, 5 training bots, vs BASE on the same seeds
Config: `tier3x:{"x_narrow":true,"x_air_eq":0.45,"t3_river_solver":true,"river_max_iters":110,"river_box_mult":50,"river_budget_s":0.08,"t3_river_narrow":true,"narrow_n0":0.001,"t3_river_rnr":true,"rnr_pmax":0.9,"rnr_n0":10,"rnr_min_n":10,"rnr_dir":-1}` (shipped box: drop river_max_iters/box_mult/budget keys).
* Locks off chips: conv +0.08 +- 0.21, trapper -0.32 +- 0.19 (-1.7 SE), exploiter 0.00 +- 0.16, **lag +1.78 +- 0.44 (z 4.0)**, minraise +0.40 +- 0.17 (z 2.4); **sum +1.94 +- 0.57 (z 3.4)**, no bot down > 2 SE: PASS.
* Locks on mean match score (`lab.opps.score_compare`: KEEP-score): BASE 0.798 -> D4 0.808, diff +0.010 +- 0.023 (z +0.4) (conv 0.51 -> 0.66, trapper 0.97 -> 0.91): PASS. (locks-on chips sum +0.02 +- 0.25.)
* **KEEP (flag still off in DEFAULTS; manager decides the flip + embed).** Not run: held-out bots, d_new_rules, Stage 2.

## Timing and coverage (exclusive lock, shipped box 40 ms x3.9, 2x clock stand-in, extra = D4 flags, vs same-seed Tier 3)
* Ratio 400h: station x1.338/1.340 (2 reruns; first run x1.362 had one 258 ms spike), trapper x1.325, conv x1.180; 1000h: x1.339 / x1.360 / x1.171. All <= 1.4, 0 deadline hits in the clean runs, worst reply 22-26 ms.
* Coverage (`lab/rf_cov.py`, tier3x + solver, box not pinned, 400h): full solves 100 % in all six cells (station 399, trapper 228, conv 139 river decisions; x1 clock 307/332/358 passes, x2 clock 137/129/153). Nothing to fix.
Commit: see `git log tier4/rf` (handoff commit).
