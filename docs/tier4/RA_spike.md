# RA: river solver spike (Opus, ~1 day, go/no-go)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/TIER4_PLAN.md` §R (budget, R0, ranges), `bot/timing.py`,
`bot/sim/inference.py` (`log_weights`), `lab/cfr/exact.py` (the reference solver). Branch `tier4/r` from
`origin/tier4/base`. Files: `bot/strategy/river_solver.py` (new), `lab/river_bench.py` (new), `tests/test_river_solver.py`,
`docs/reports/TIER4_RIVER.md`. Nothing under `bot/cfr/` (the teammate's).

**Why a spike first:** a decision's budget is ~4.5–5.4 ms and the hard deadline is 80 ms (→ Tier 0). The plan gives
the river a time box of 4 × the budget, ≤ 20 ms on this laptop (≈ half the iterations on the 2× server). The solver
must be useful inside that.

## Tasks
1. **Solver** (`bot/strategy/river_solver.py`, NumPy only): vector CFR+ for one river decision. Inputs: our range and
   their range as weights over 2-card combos (≤ 903 each, card removal with the board and both public discards),
   the pot, the stacks, the current bet, and the action menu: ½ pot / pot / all-in, ≤ 2 raises, starting from the
   current node with the real amounts (off-tree sizes are fine). Showdown and fold values in O(n) per terminal with
   card removal (sort by hand rank; per-card sums). **Anytime:** a deadline argument; it returns the current average
   strategy for our actual hand at the root, plus the iteration count, and never runs past the deadline.
2. **Ranges for the spike:** their range from `Inference.log_weights` over the 903 combos (the discard is known by the
   river); ours, for now, uniform over combos consistent with our public discard (RB builds the real one). Time the
   range building too: it counts toward the box.
3. **Correctness:** on reduced-deck toy rivers, the solver's strategy has exploitability ≤ 2 % of the pot, computed by
   `lab/cfr/exact.py` (or by a vector best response inside the solver, checked against `exact.py` on one toy case).
   Tests in `tests/test_river_solver.py`: toy exploitability, the deadline is respected, card removal (no combo uses
   a board or discarded card), output sums to 1 over legal actions.
4. **Speed** (`lab/river_bench.py`): iterations per ms on 200 real river spots from S0's recordings, or from a few
   `lab.harness` matches if S0 isn't ready. **Go if ≥ 50 iterations fit in 10 ms on this laptop, range building
   included.**
5. If the full version misses: try the reduced one before giving up (prune combos with near-zero weight, one showdown
   ranking per river shared by all terminals, sizes pot + all-in only, warm start). Report both.

**Provisional (cloud):** the GO is a cloud number. RB's step 0 re-runs the bench on the laptop and makes it final.

## Done when
- `docs/tier4/handoff/RA.md`: **GO or NO-GO**, iterations per 10 ms (full and reduced), exploitability on toy rivers,
  the solver's API (signature), the commit. On NO-GO, R stops; I1 keeps Tier 3's river.
