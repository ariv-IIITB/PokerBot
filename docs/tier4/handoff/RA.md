# RA handoff: river solver spike

**GO for the reduced (bucketed) solver; the full exact-combos version is NO-GO.** Tables: `docs/reports/TIER4_RIVER.md`;
raw output `logs/river_bench_RA_*.txt`. Code commit `86c0920`. The session was assigned branch `claude/zen-ptolemy-4w0rqi`
(from `origin/tier4/base`), not `tier4/r`: RB branches from it. Machine: Intel Xeon @ 2.30 GHz, nproc 4, Py 3.11, float32;
200 real river spots (Tier 3 vs four pool bots).

## Passes in a 20 ms box (ranges + setup included, median) and exploitability (pot = 1, exact full game)
| variant | passes | spots >= 100 | exploitability |
|---|---|---|---|
| exact 990/903 combos, 1/2 - pot - all-in | 6 | 0 % | 0.83 ± 0.28 (unconverged) |
| exact, pot + all-in only | 10 | 0 % | 0.68 ± 0.26 |
| pruned to 300 combos, pot + all-in | 61 | 12 % | 0.042 ± 0.012 (pruned game) |
| 64 buckets, 1/2 - pot - all-in | 152 | 77 % | 0.0176 ± 0.003 |
| **64 buckets, pot + all-in only** | **249** | **100 %** | **0.0095 ± 0.001** (max 0.021, 30 spots) |
2x-slower stand-in (10 ms box): 64 buckets pot + all-in 72 passes (0.018 ± 0.002). Against passes (same variant):
25 -> 0.065, 50 -> 0.029, 100 -> 0.015, 200 -> 0.011, floor 0.008 (bucketing loss). Toy rivers: <= 0.02 pot by
`lab/cfr/exact.py` after 400 passes (4 spots x 2 kernels); the solver's vector best response agrees to 1e-6.
Range building 3.8 ms of the box: their range via `Opponent.range_weights` 2.5 ms (weights are flat, so pruning is
arbitrary), ranks 1.3 ms. Setup 1.5 ms, then 0.06 ms/pass.

## API (`bot/strategy/river_solver.py`)
`solve_river(spot: RiverSpot, hero_cards, hero_w, hero_rank, opp_cards, opp_w, opp_rank, hero_index, deadline,
cfg=TreeCfg(), max_iters, min_iters=0, keep_solver=False, dtype=np.float32, buckets=0, kernel="auto", track_all=False)
-> SolveResult(labels, probs, iterations, setup_s, run_s, solver) | None`
* `deadline` = absolute `perf_counter()`; None if no pass fit. `labels` = root actions `("F"|"C"|"K"|"R", level)`, for
  "R" the level is our street total (the engine's raise-to). `probs` = average strategy of our hand's bucket.
* `RiverSpot(pot, hero_bet, opp_bet, hero_stack, opp_stack, last_raise, aggr_so_far, checked)` = `h.pot, h.my_bet,
  h.opp_bet, h.my_stack, h.opp_stack`, `h.tocall` if > 0, raises on the street, their last action was a check.
* Use `buckets=64, cfg=TreeCfg(bet_sizes=(1.0, INF), raise_sizes=(1.0, INF))`. Ranges: (n, 2) card ids + weights +
  `hand_ranks(evaluator, combos, board)`; `combos_excluding(dead)`. `lab/river_bench.py` is the reusable harness.

## For RB
* Our range is uniform here; building the real one is RB's job. A cheaper opponent range (cache strengths per board)
  would free part of the 3.8 ms. The abstraction has no card removal; exploitability is against the given ranges.
* Tests: `tests/test_river_solver.py` 20 passed; fast suite 1310 passed, 2 skipped; `test_timing_slow.py` 10 passed.
  Nothing imports the solver yet, so Tier 3's timing is unchanged. Seeds 50000+ (lab matches for the spots; read only).
