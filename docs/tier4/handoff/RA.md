# RA handoff: river solver spike

**Decision: GO for the reduced (bucketed) version; the full exact-combos version is NO-GO.** On GO, RB builds on the
bucketed solver below. Details and tables: `docs/reports/TIER4_RIVER.md`; raw output `logs/river_bench_RA_*.txt`.

Branch: the session was assigned `claude/zen-ptolemy-4w0rqi` (from `origin/tier4/base`), not `tier4/r`. RB should
branch from it (or from the commit below) and use `tier4/r` afterwards. Code commit: `86c0920`.
Machine: Intel Xeon @ 2.30 GHz, nproc 4, Python 3.11, float32. 200 real river spots from Tier 3 vs four pool bots.

## Numbers (passes in a 20 ms box, range building + setup included; median; exploitability in pot units)
| variant | passes | spots with >= 100 | exploitability, exact full game |
|---|---|---|---|
| exact 990/903 combos, 1/2 - pot - all-in | 6 | 0 % | 0.83 ± 0.28 (unconverged) |
| exact, pot + all-in only | 10 | 0 % | 0.68 ± 0.26 |
| pruned to 300 combos, pot + all-in | 61 | 12 % | 0.042 ± 0.012 (pruned game) |
| 64 buckets, 1/2 - pot - all-in | 152 | 77 % | 0.0176 ± 0.003 |
| **64 buckets, pot + all-in only** | **249** | **100 %** | **0.0095 ± 0.001** (max 0.021, 30 spots) |
| 32 buckets, pot + all-in only | 290 | 100 % | 0.0090 ± 0.001 |
Stand-in for the 2x slower server (10 ms box): 64 buckets pot + all-in 72 passes (0.018 ± 0.002), 64 buckets 1/2-pot-all-in 39.
Exploitability vs passes (64 buckets, pot + all-in): 25 -> 0.065, 50 -> 0.029, 100 -> 0.015, 200 -> 0.011, floor 0.008
(the bucketing loss). Toy rivers (`lab/cfr/exact.py`, 4 spots x 2 kernels): <= 0.02 pot after 400 passes; the vector
best response agrees with `exact.py` to 1e-6.
Range building: their range via `Opponent.range_weights` 2.5 ms (flat weights: all 903 combos above 1e-3 of the max),
ranks 1.3 ms, total 3.8 ms of the box; setup 1.5 ms (buckets), 0.06 ms/pass.

## API (`bot/strategy/river_solver.py`)
`solve_river(spot: RiverSpot, hero_cards, hero_w, hero_rank, opp_cards, opp_w, opp_rank, hero_index, deadline,
cfg=TreeCfg(), max_iters, min_iters=0, keep_solver=False, dtype=np.float32, buckets=0, kernel="auto", track_all=False)
-> SolveResult(labels, probs, iterations, setup_s, run_s, solver) | None`
* `deadline` = absolute `time.perf_counter()`; None if no pass fit. `labels` = root actions `("F"|"C"|"K"|"R", level)`;
  for "R" the level is our street total (= the engine's raise-to). `probs` = average strategy of our hand (its bucket).
* `RiverSpot(pot, hero_bet, opp_bet, hero_stack, opp_stack, last_raise, aggr_so_far, checked)` = `h.pot, h.my_bet,
  h.opp_bet, h.my_stack, h.opp_stack, h.tocall (if > 0), raises on the street, their last action was a check`.
* Use `buckets=64, cfg=TreeCfg(bet_sizes=(1.0, INF), raise_sizes=(1.0, INF))`. Ranges are 2-card combos (n, 2) card ids
  with weights and `hand_ranks(evaluator, combos, board)`; `combos_excluding(dead)` lists combos avoiding dead cards.
* `lab/river_bench.py` (`record_spots`, `build_inputs`, `exploit_after`) is the harness RB can reuse.

## What RB needs to know
* Our range is uniform here: building the real one (and a cheaper opponent range, e.g. cache hand strengths per board)
  is RB's job. The 3.8 ms of range building is 19 % of the box.
* The abstraction has no card removal and plays a bucket's strategy for each hand in it; exploitability above is
  against the given ranges, not against the real opponent.
* Off-tree sizes need no action: the tree starts at the real amounts. Hard deadline (80 ms) is far above the box.
* Tests: `tests/test_river_solver.py` 20 passed; fast suite 1310 passed, 2 skipped; `tests/test_timing_slow.py` 10 passed
  (nothing imports the solver yet, so Tier 3's timing is unchanged; no `lab.timing_bench` run needed).
* Seeds used: 50000+ for the lab matches that supplied the river spots (not in a block; read only).
