# Tier 4, stream R: river solver spike (RA)

Question: can a live CFR+ solver for one river decision fit in the time box (4 × the decision budget, ≤ 20 ms,
ranges included), and is it close enough to equilibrium to be worth wiring into Tier 3's river?
**Answer: GO for a reduced version; NO-GO for the full one.** Raw output: `logs/river_bench_RA_*.txt`.

Machine: Intel Xeon @ 2.30 GHz, nproc 4, Python 3.11, NumPy float32. Reproduce:
`.venv/bin/python -m lab.river_bench --spots 200 --box-ms 20 --expl 30` (and `--box-ms 10` as the stand-in
for a server 2× slower: ranges and setup then take the same share of the box as 2× the time in a 20 ms box).

## What was built
`bot/strategy/river_solver.py` (NumPy only, ~600 lines), `lab/river_bench.py`, `tests/test_river_solver.py` (20 tests).

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
A pass is ~15–30 decision nodes × 903–990 hands: the terminals alone (≈ 2 × 14 showdowns and 14 folds) cost 0.5–1 ms
in float32 even with O(n) removal, and the rest of the pass touches ~100 k floats per node-level. 100 passes need
~0.2 ms/pass; the exact game is 4–9× over that before ranges and setup, and ranges alone eat 3.8 ms of the 20.
Pruning does not help much because the inferred weights are flat; the dense kernel at 300 combos reaches ~0.24 ms/pass
with the small tree but still only 61 passes.

## Caveats for RB / RC
* The solver plays an **abstraction**: with buckets our hand's strategy is its bucket's. Real-game exploitability of the
  translated strategy is what is quoted above; against a real opponent (not a best response) it will be lower.
* Numbers are exploitability **against the given ranges**. Our range here is uniform; the real own range (RB) is the
  main risk (see the plan), and the opponent range is only as good as `Inference`.
* Inference is 2.5 ms of the box (the second largest item after the solve): RB should cache the strength of the 903
  combos per board, or score only the bucketed range.
* The first pass costs ~2–3× a steady pass (cold arrays); included in the pass counts above.
* The `tree N decisions` figure in the bench lines is the first spot's, not a median.
* Nothing in `bot/` imports the module yet, so Tier 3's timing is unchanged (fast suite 1310 passed, 2 skipped;
  `tests/test_timing_slow.py` 10 passed on this machine).
