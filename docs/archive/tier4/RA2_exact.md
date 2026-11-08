# RA2: river solver as close to exact as the time box allows (Opus, cloud)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, and on branch `origin/tier4/r`: `docs/tier4/handoff/RA.md`,
`docs/reports/TIER4_RIVER.md`, `bot/strategy/river_solver.py`, `lab/river_bench.py`, `tests/test_river_solver.py`.
Branch: start from `origin/tier4/r` (RA's solver). Seeds: RA's recorded spots only (no new matches needed).
`--processes` per README rule 3.

**Files: only `bot/strategy/river_solver.py`, `lab/river_bench.py`, `tests/test_river_solver.py`,
`docs/reports/TIER4_RIVER.md` (append an RA2 section).** RB is working on the same stream at the same time (own range,
Tier 3 hook, timing) and calls `solve_river(...)`: **keep `solve_river`'s signature and `SolveResult` unchanged** (new
options only as keyword arguments with defaults that keep today's behaviour). Don't touch RB's files.

## Goal
RA's chosen variant (64 buckets, pot + all-in) is ~1 % of the pot away from the exact game (floor 0.8 %, from bucketing),
at 249 passes in 20 ms and 72 in the 10 ms stand-in for the 2× slower server. **Get as close to the exact game as
possible.** Report exploitability against box size (10, 20, 40, 80 ms; the 10 ms box stands in for 20 ms on the 2×
slower server), so RB can pick the largest box the time bank allows (README: spend the safe time). Aim for median
exploitability **≤ 0.3 % of the pot in the exact full game** at 10 ms, and as low as reachable at larger boxes; keep
going until a step stops helping, not until the target is met. Exploitability is measured the way RA's bench does
(exact best response in the full, unbucketed game, against the given ranges).

## Steps (measure after each with `lab/river_bench.py`; keep a step only if it lowers exploitability at 10 ms)
1. **Cheaper ranges:** RA measured 3.8 ms of the box on range building (2.5 ms in `Opponent.range_weights`, 1.3 ms on hand
   ranks). Cache hand ranks per board inside the solver call path, and vectorise what's left. Every ms saved is passes.
2. **Better buckets:** more buckets (128, 256) and bucketing by features that keep card removal (rank within the board
   plus blocker counts), instead of rank alone. Report the floor (exploitability at many passes) and the 10 ms number
   for each.
3. **Card removal inside buckets:** in showdown and fold values, use the per-card sums RA already has for the exact
   kernel, so bucketed play no longer ignores blockers.
4. **Exact when affordable:** if both ranges have few enough live combos after weighting (find the cut-off from the
   bench: where the dense exact kernel reaches ≥ 50 passes in 10 ms), solve exact instead of bucketed.
5. **Bet sizes:** add ½ pot back if, after steps 1–4, it improves exploitability at 10 ms (more sizes = less abstraction
   error but fewer passes).
6. **Faster convergence:** warm start from a cheap prior (e.g. Tier 3's river policy, or the strategy of the bucket at
   the previous solve); try discounted CFR (DCFR, α 1.5, β 0, γ 2) against CFR+ with t² averaging. Keep whichever is
   lower at 10 ms.
7. **Reuse within a hand:** with `keep_solver=True`, a later river decision in the same hand continues the earlier solve
   instead of starting over. Measure on bench spots that have two of our river decisions.

## Tests
Every existing test still passes (same API). Add: cached ranks equal the uncached ones; the card-removal bucket kernel
matches the exact kernel when each bucket holds one combo; exact-mode switch picks exact below the cut-off; the deadline
is still never exceeded; DCFR (if kept) passes the toy-river exploitability test.

## Done when
- `docs/tier4/handoff/RA2.md` (≤ 40 lines): a table per step (passes and exploitability at 20 ms and 10 ms, ± SE, 30
  spots), what was kept, the final default settings, the machine, the commit, and the branch name you pushed.
- Fast suite green; `tests/test_timing_slow.py` passes. Nothing outside the four files above changed.
- If the 0.3 % target isn't reached, report the best reached and what limits it (abstraction floor vs passes).
