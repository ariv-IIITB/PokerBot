# Tier 4, stream R: river solver spike (RA)

Question: can a live CFR+ solver for one river decision fit in the time box (4 × the decision budget, ≤ 20 ms,
ranges included), and is it close enough to equilibrium to be worth wiring into Tier 3's river?
**Answer: GO for a reduced version; NO-GO for the full one.** Raw output: `logs/river_bench_RA_*.txt`.

Machine: Intel Xeon @ 2.30 GHz, nproc 4, Python 3.11, NumPy float32. Reproduce:
`.venv/bin/python -m lab.river_bench --spots 200 --box-ms 20 --expl 30` (and `--box-ms 10` as the stand-in
for a server 2× slower: ranges and setup then take the same share of the box as 2× the time in a 20 ms box).

## What was built
`bot/strategy/river_solver.py` (NumPy only, 605 lines), `lab/river_bench.py`, `tests/test_river_solver.py` (20 tests).

* **Tree** from the engine's own numbers: pot, both street bets, both stacks behind, last raise size, bets so far,
  whether they checked. Menu fold / call / check, bets and raises of pot fractions and all-in (default ½ / 1 / all-in,
  or 1 / all-in), ≤ 3 bets+raises on the street (a bet and 2 raises), effective stack caps all-in, a bet above the
  shorter stack is refunded. Payoffs include the sunk pot (zero-sum), in pot units.
* **Vector CFR+**, simultaneous updates, linear-in-t² averaging (a measured 15 % gain over t at 100 passes), regrets
  floored at 0. Tree in BFS order, so a pass is ~60 NumPy calls whatever the range size (reach, values, regrets).
  Only the root average is kept in live mode (`track_all=True` keeps all of them, for exploitability).
* **Terminals with card removal in O(n)** (`SortedKernel`: prefix sums over combos sorted by rank, per card, by
  inclusion-exclusion; the combo equal to our hand has sign 0 so no correction), a `DenseKernel` (matrix products,
  exact removal, best up to a few hundred combos) and a **bucket kernel** (`bucket_ranges` + `bucket_kernel`: equal-mass
  strength buckets per player, expected sign between buckets, no card removal).
* **Anytime:** `solve_river(..., deadline)` checks `perf_counter` every pass; returns `None` if not one pass fit.
* **Exploitability:** `RiverSolver.exploitability()` = (BR₀ + BR₁)/2 by a vector best response over the same tree,
  also for a strategy translated from the bucketed game to the exact full game (`kernel=`, `weights=`).

## Correctness
* Toy rivers (7 free cards → 21 combos each, real evaluator, non-uniform ranges), 4 spots (we act first, they checked,
  facing a bet, short stacks / 3 bets) × both exact kernels: **exploitability by `lab/cfr/exact.py` ≤ 0.02 pot** after
  400 passes, and the solver's own vector best response agrees with `exact.py` to 1e-6.
* Terminal values of both kernels equal a brute-force matrix; the bucket kernel equals the weighted mean sign.
* No combo uses a board or discarded card (`combos_excluding`), root strategy sums to 1, the deadline is respected.

## Speed: 200 real river spots (Tier 3 vs d_new_trapper / d_conv_opp3 / d_new_lag / d_new_exploiter, 200-hand matches)
Range building is paid by every variant: **their range** = `Opponent.range_weights` over the 903 combos (the same
inference Tier 3 uses) **2.5 ms** (p90 3.1) + showdown ranks of both ranges 1.3 ms + combos 0.07 ms = **3.8 ms**.
Our range is uniform over the 990 combos consistent with our public discard (RB builds the real one).
Inference weights are nearly flat: all 903 combos stay above 1e-3 of the max, so pruning by weight is arbitrary.

Passes inside a 20 ms box, ranges + setup included (median, share of spots with ≥ 100):

| variant | n per side | passes | ≥ 100 | ms/pass | exploitability in the exact full game (pot = 1) at that count |
|---|---|---|---|---|---|
| full: exact combos, ½/1/all-in | 990/903 | 6 | 0 % | 1.7 | 0.83 ± 0.28 (not converged) |
| exact, pot + all-in only | 990/903 | 10 | 0 % | 0.79 | 0.68 ± 0.26 |
| pruned to 300 combos, ½/1/all-in | 301/300 | 28 | 6 % | 0.51 | 0.11 ± 0.04 (in the pruned game) |
| pruned to 300, pot + all-in | 301/300 | 61 | 12 % | 0.24 | 0.042 ± 0.012 (pruned game) |
| **64 buckets, ½/1/all-in** | 64/64 | **152** | 77 % | 0.09 | **0.0176 ± 0.003** |
| **64 buckets, pot + all-in** | 64/64 | **249** | **100 %** | 0.06 | **0.0095 ± 0.001** (max 0.021) |
| 32 buckets, pot + all-in | 32/32 | 290 | 100 % | 0.05 | 0.0090 ± 0.001 (max 0.028) |
| 16 buckets, pot + all-in | 16/16 | 316 | 100 % | 0.05 | 0.015 ± 0.003 (max 0.076) |

Stand-in for the 2× slower server (10 ms box): 64 buckets pot + all-in **72** passes (exploitability 0.018 ± 0.002,
max 0.048); 32 buckets pot + all-in 95 passes (0.015 ± 0.002); 64 buckets with ½/1/all-in only 39 (0.060 ± 0.012).

Exploitability against passes (64 buckets, pot + all-in, translated to the exact full game, 30 spots):
25 → 0.065, 50 → 0.029, 100 → 0.015, 200 → 0.011, 400 → 0.009, 3000 → 0.008. The floor (~0.8 % of the pot) is the
loss from bucketing (card removal and hand identity inside a bucket); the rest is not converged.

## Why the full version misses
A pass costs 0.8 ms (pot + all-in tree) to 1.7 ms (½/1/all-in) median at 990/903 hands in float32, even with O(n)
card removal (profile: the showdown/fold kernels ~40 %, the rest is the strategy, reach, value and regret tensors).
100 passes in 20 ms need ≤ 0.12 ms/pass after 3.8 ms of ranges and ~1.5–6 ms of setup: the exact game is 7–14× over.
Pruning does not help much because the inferred weights are flat; the dense kernel at 300 combos reaches ~0.24 ms/pass
with the small tree but still only 61 passes.

## Caveats for RB / RC
* The solver plays an **abstraction**: with buckets our hand's strategy is its bucket's. Real-game exploitability of the
  translated strategy is what is quoted above; against a real opponent (not a best response) it will be lower.
* Numbers are exploitability **against the given ranges**. Our range here is uniform; the real own range (RB) is the
  main risk (see the plan), and the opponent range is only as good as `Inference`.
* Inference is 2.5 ms of the box (the second largest item after the solve): RB should cache the strength of the 903
  combos per board, or score only the bucketed range.
* The first pass costs ~1.9× a steady pass for the bucketed game (0.11 vs 0.06 ms) and ~1.2× for the exact one (cold
  arrays); included in the pass counts above.
* The `tree N decisions` figure in the bench lines is the first spot's, not a median.
* Nothing in `bot/` imports the module yet, so Tier 3's timing is unchanged (fast suite 1310 passed, 2 skipped;
  `tests/test_timing_slow.py` 10 passed on this machine).

# RA2: the river solver as close to exact as the box allows

Machine: Intel Core Ultra 5 225H, nproc 14 (shared; every timing run held the laptop lock, one BLAS thread to model the
1-vCPU server), Python 3.11. 60 real river spots (Tier 3 vs the four pool bots), **pinned in one pickle so every variant and
box sees the same spots, timed back to back in one run**. Exploitability = best response in the exact full game (990/903
combos, same tree), pot = 1, mean ± SE over the 60 spots (median in brackets); "passes" = median inside the box with the
ranges (3.0 ms: inference 2.5 + ranks 0.5) and setup included. Raw: `logs/river_bench_RA2_*.txt` (kept in the notes folder,
not committed). Reproduce: `.venv/bin/python -m lab.river_bench --spots 60 --spots-file S.pkl --box-ms 10,20,40,80
--variants bucket64/small-tree,bucket64cr/small-tree,auto/small-tree --expl 60 --lock`.

## Result: box-size curve (the numbers RB needs)
| box | RA (64 equal-mass buckets, float32) | + card removal (64 buckets) | **final: `auto=True`** | final settings |
|---|---|---|---|---|
| 10 ms | 154 passes, 0.0177 ± 0.0053 (0.0108) | 132, 0.0167 ± 0.0059 (0.0087) | **144, 0.0098 ± 0.0010 (0.0082)** | 48 buckets |
| 20 ms | 402, 0.0091 ± 0.0008 (0.0085) | 360, 0.0058 ± 0.0007 (0.0042) | **326, 0.0057 ± 0.0006 (0.0046)** | 64 |
| 40 ms | 892, 0.0079 ± 0.0007 (0.0068) | 815, 0.0036 ± 0.0004 (0.0026) | **730, 0.0038 ± 0.0005 (0.0028)** | 64 |
| 80 ms | 1888, 0.0076 ± 0.0007 (0.0065) | 1706, 0.0030 ± 0.0004 (0.0020) | **1114, 0.0030 ± 0.0004 (0.0019)** | 96 |

So exploitability falls from ~1.8 % (10 ms) / 0.9 % (20 ms) to **0.98 % / 0.57 %**, and to 0.38 % at 40 ms and 0.30 % at 80 ms.
The RA bucketing floor (0.65 %) is gone, which is why the curve now keeps falling with the box. **The ≤ 0.3 % target at 10 ms is not
reached**: the limit is passes, not the abstraction. CFR+ error goes as ~1/passes (128 buckets, same 30 spots: 25 → 0.058,
50 → 0.028, 100 → 0.014, 200 → 0.0085, 400 → 0.0050, 800 → 0.0032, 3000 → 0.0022 = the floor), and a 10 ms box holds ~145
passes. 0.3 % needs ~800 passes, i.e. a ~40 ms box. Passes if the ranges were free: 226 in the 10 ms box (inference alone
is 2.5 ms of it: that is RB's and `Opponent.range_weights`'s, not this file's).

## Steps (kept = lowers exploitability at 10 ms or removes a risk)
| # | step | result | |
|---|---|---|---|
| 1 | ranks: one evaluation per combo (cache keyed by board; our range ⊂ theirs + 2 cards; later river decision of a hand: free) | 0.63 → 0.48 ms cold, 0.06 ms warm | kept |
| 1 | bucket kernel: `np.add.at` over (hero combo × bucket) replaced by exact signs outside the overlap band + member sums inside it | setup kernel 3.0 → 0.23 ms (64 buckets), 0.76 ms (128) | kept |
| 2–3 | **card removal in buckets**: pair-sharing mass from per-bucket card histograms (one B×52×B product), scales the sign matrix, gives the fold matrix; exact when each bucket is one combo (tested) | floor (3000 passes, 30 spots): 64 buckets 0.0065 → 0.0030; 128: 0.0021; 256: 0.0016; 512: 0.0008. At the box: 20 ms 0.0091 → 0.0058, 40 ms 0.0079 → 0.0036 | kept |
| 2 | bucket count by box (float64, 60 spots, other sample): 10 ms: 24 → 0.0145, 32 → 0.0129, **48 → 0.0123**, 64 → 0.0135, 96 → 0.0181; 20 ms: 48 → 0.0070, **64 → 0.0064**, 96 → 0.0078; 40 ms: 48/**64**/96 = 0.0039/0.0038/0.0040, 128 → 0.0052, 192 → 0.0076; 80 ms: 64/**96**/128 = 0.0030/0.0028/0.0031 | `AUTO_BUCKETS` = 48 below 12 ms, 64 below 60 ms, else 96 | kept |
| 2 | buckets that never mix hand values (a river range has 30–130 distinct values of 903) | floor unchanged (128: 0.0021) | dropped |
| 4 | exact when affordable: with `auto`, zero-weight combos are dropped and if both ranges fit in the bucket count the exact dense kernel is used (equal to one-combo buckets, same cost) | tested; the real ranges (903/990 live) never qualify, a restricted range would | kept |
| 5 | ½ pot back (48 buckets, own game): 10 ms 0.0312, 20 ms 0.0102, 40 ms 0.0058, 80 ms 0.0042 vs 0.0103 / 0.0053 / 0.0038 / 0.0034 for pot + all-in | passes 104 vs 154 at 10 ms | dropped |
| 6 | PCFR+ (predictive), DCFR(1.5, 0, 2), alternating updates, averaging power 1/2/3/5, coarse-to-fine warm start (16 → 128 buckets), 64 buckets, 100 passes: CFR+ t² 0.0114; PCFR+ 0.0116; DCFR 0.0205; alternating 0.0242 vs 0.0143 (128); power 0.0137/0.0114/0.0110/0.0114; warm start 0.0098 vs 0.0095 at equal passes | none beats CFR+ with t² averaging | dropped (code removed) |
| 7 | reuse within a hand: 17 % of our river decisions are a second one (35 of 200); they are already easy (small tree): 10 ms 0.0048 ± 0.0014 vs 0.0110 ± 0.0011 for first decisions (11 / 49 spots); the rank cache makes their ranges free | no regret reuse (nothing to gain) | cache only |
| – | **float64 in `auto`**: float32 is no faster at these sizes (median ratio 0.96 at 32 buckets, 0.91 at 64) and hits denormals (reach products ~1e-40) on 5–8 % of spots, up to 3.4× slower per pass, which gave 0.3–1.7 pot outliers at 10 ms with 96–128 buckets | 10 ms mean: float32 0.0103 ± 0.0015 (max 0.086) vs float64 0.0098 ± 0.0010 (max 0.048) | kept |

## API (unchanged signature; new keyword arguments, defaults keep today's behaviour)
`solve_river(..., card_removal=False, auto=False)`. **`auto=True`** is the final setting: float64, zero-weight combos dropped,
exact dense if both ranges fit `auto_buckets(time left)`, else card-removal buckets (48 / 64 / 96 by the time left after the
ranges, `AUTO_BUCKETS`), `deadline` as before. Use it with `cfg=TreeCfg(bet_sizes=(1.0, INF), raise_sizes=(1.0, INF))`.
`hand_ranks` caches the last board (also what makes a second decision's ranges free). `build_game(...)` is the same setup
without running (the bench uses it). Tests: 25 in `tests/test_river_solver.py` (cached ranks equal direct, card-removal kernel
equals the exact kernel with one combo per bucket, `auto` exact below the bucket count, our hand kept at zero weight,
deadline respected, exploitability < 3 % after 300 passes). Fast suite 1314 passed, 2 skipped; `test_timing_slow.py` 10 passed.
Caveats: the first solve in a process runs a few passes slower (cold arrays); times are on this laptop, the server is ~2×
slower, so the 10 ms row is the 20 ms server box. Our hand's strategy is its bucket's, as before.

## RC: the solver in Tier 3's river, gate R (stage 1; the restricted river is NOT done)

Machine: Intel Core Ultra 5 225H, nproc 14, shared with PB/DA evals (turnstile + laptop lock), Python 3.11.

**What changed.** RB's hook now calls `solve_river(..., auto=True, cfg=TreeCfg(bet_sizes=(1.0, INF), raise_sizes=(1.0, INF)))` on the
**full** ranges (990 / 903 combos): the 300-combo sampling and the 150-pass cap are gone (`river_combos`, `river_buckets`
removed; `river_max_iters` is back as a lab-only knob, default 0 = no cap). Per-decision costs on 40 recorded spots, laptop speed, median
(p90): their range 1.9 ms (2.4), our own range 1.3 ms (1.8), ranks 0.45 ms, so ~3.6 ms before the solve: RB's own-range build is not a
bottleneck and was not optimised. Every spot got >= 20 passes in a 10 ms box (median 124 passes at 10 ms, 314 at 20 ms, 747 at 40 ms).
`lab/rc_range_bench.py`. No start-up dummy solve: the cold first solve costs a few passes once per match.

**Time box (the 2x-slower stand-in, `lab/rc_ratio.py`).** Same as `tests/test_river_timing.py`: the lab engine charges every second twice and
the wall-clock box is halved. `lab.timing_bench` can't carry a brain config over its subprocess path (a first run with `tier3:{...}` silently
ran plain Tier 3), so the harness is used. Bank use flag on / flag off (400 hands; calling_station / trapper): box = mult x budget, mult 3 -> x1.19 / x1.21,
3.5 -> x1.27 / x1.29, 4 -> x1.34 / x1.37; the ceiling (`river_budget_s`) never binds at 40 ms or 80 ms, the multiplier does. **Shipped values:
`river_box_mult` 3.9, `river_budget_s` 0.040** (RB had 4.0 / 0.020). Hard deadline unchanged (the box stays < max(80 ms, 6 x budget) and
the hard limit is >= 2 x box; `tests/test_river_hook.py`). Final check on the final code, 1000 hands: **x1.328 (31 % of bank) and x1.288 (19 %)**,
deadline hits 0 -> 0, emergency 0, worst reply 25 ms, 142 / 121 passes, 0 fallbacks. Not past the 1.35 target, below 1.4.
The curve above 40 ms (laptop speed) is flat (RA2), so the box is not raised further.

**Margin check (task A, `lab/rc_margin.py`, shipped config, 2x stand-in, exclusive lock).** River decisions, 400 hands, calling_station / trapper:
wall time p50 10.5 ms, p99 10.5-10.6 ms, max 10.7 ms (x2: 21.3 ms) against a hard limit of 80 ms: **max / limit 0.13 (x2: 0.27) <= 0.5, no change
to the hard limit.** (Non-river decisions: max 20.6 ms wall, 41 ms x2 = 0.52 of 80 ms once, on calling_station: a Tier 3 discard/flop spike, baseline code, not the solver.)

**Gate R** (flag on vs plain `tier3`, seeds 30000-30049, 50 pairs per point, discard_holdem). The ON arm pins the solve by passes
(`river_max_iters` 110, ceiling 80 ms) instead of the halved wall-clock box. Reason: under the gate's CPU contention (6 + other sessions' processes, nice)
the wall-clock box fell back to Tier 3's river on **56 %** of river decisions (2 pairs vs conv_opp3: 325 solves, 420 no-pass + 52 few-pass fallbacks, median 45 passes).
Those outputs are kept in `logs/rc/gate_walltime_invalid/` and not used. Pinned arm fire check: 722 solves, 0 fallbacks, 110 passes. 110 = what the unloaded
2x-stand-in runs give (100-140). So **gate R tests the solver at its unloaded 2x-server behaviour; under heavy contention the shipped time box falls back to
Tier 3's river on a large share of decisions (safe, no gain).**

| item | result | |
|---|---|---|
| head to head vs `tier3`, score >= 0.5 - 2 SE | 0.490 +- 0.050 over 100 matches (bar 0.40); chips -0.00 +- 0.02 | PASS |
| training pool, chips, locks off (sum up, no bot down > 2 SE) | sum +0.27 +- 0.50; conv_opp3 +0.43 +- 0.20 (z +2.1), exploiter +0.04 +- 0.26, lag -0.06 +- 0.27, minraise -0.06 +- 0.13, rules -0.05 +- 0.15, trapper -0.03 +- 0.16 | PASS |
| training pool, match score, locks on (not lower by > 2 SE) | 0.623 -> 0.643, +0.020 +- 0.021 (z +0.9) | PASS |
| combined river buckets better by > 2 SE vs conv_opp3 and exploiter | conv_opp3 +0.497 +- 0.270 (z +1.8); exploiter +0.084 +- 0.270 (z +0.3) | **FAIL** |
| timing ratio <= 1.4 | x1.33 / x1.29 at 1000 hands (above) | PASS |

By the letter gate R = FAIL; `t3_river_solver` stays off in `DEFAULTS`. **Own-range caveat (RB's sensitivity check): 20 % of spots move the solver's EV
by more than 0.20 pot depending on our assumed range (mean 0.146 +- 0.022 pot).** The range our line implies is the weakest input.

**Extension** (manager's request, only the two bots that decide the failing item; fresh seeds 30100-30149, locks off, 50 pairs, final code):
chips conv_opp3 -1.30 -> -1.38 (-0.08 +- 0.21), exploiter +6.03 -> +5.89 (-0.14 +- 0.25). River-all difference: conv_opp3 -0.121 +- 0.266 (z -0.5), exploiter -0.015 +- 0.261 (z -0.1).
Pooled over all 100 pairs (equal weights): conv_opp3 +0.188 +- 0.189 (z +1.0), exploiter +0.035 +- 0.188 (z +0.2). The first 50 pairs' lead on conv_opp3 does not repeat.

**Task B (middle rung in `Bot.choose`).** Tier 3 at budget 0 (solver on; 5,700 decisions over 3 opponents, 400 hands each): p50/p99/max ms preflop 0.05/0.19/12.7 (cold),
flop 1.19/1.47/19.6 (cold), turn 1.27/1.66/1.88, river 1.53/2.04/2.33, discard 0.88/1.13/1.24; 0 illegal actions, 0 exceptions (`lab/rc_budget0.py`).
So on a deadline hit or a brain exception `choose` now asks the brain again at budget 0 under a 30 ms deadline (`RETRY_DEADLINE_S`) and only then plays Tier 0; emergency
mode still goes straight to Tier 0. Counters `deadline_retries` / `retry_wins` (in the stderr summary). Tests in `tests/test_main.py`. The retry runs on a brain that was
interrupted mid-decision; any exception from that goes to Tier 0.

Restricted river (RNR, task 3): not built. Gate R failed, so there is nothing to build on.
