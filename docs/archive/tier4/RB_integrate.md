# RB: the solver in Tier 3's river (Opus, cloud)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/TIER4_PLAN.md` §R (R1, our range, their range),
`docs/tier4/handoff/RA.md`, `bot/brains/tier3.py` (its river section), `bot/strategy/ranges.py` (`OwnRange`),
`bot/timing.py`, `bot/main.py` (the hard-deadline fallback). Branch `tier4/r` (continue after RA's GO).
Files: the R row of the README's ownership table.

## Step 0: re-check RA's GO on your machine
Re-run `lab/river_bench.py` (your machine may differ from RA's). If it misses the GO bar
(≥ 100 iterations in 20 ms, range building included), try RA's reduced variant; if that misses too, stop and write
a NO-GO handoff.

## Tasks
1. **Our range** (`bot/strategy/own_range.py`): weights over our 2-card combos from our line on every street and our
   public discard, using the same likelihood model inference uses for the opponent. (`OwnRange` only gives a
   percentile from our preflop line.) This is an approximation: say so in a docstring. Test: a line of bets
   shifts weight toward stronger combos; the discard's card is excluded.
2. **Hook in Tier 3:** a param `t3_river_solver` (default **off**). When on, each river decision builds both ranges and
   calls the solver inside one time box = min(4 × `timer.budget()`, `river_budget_s` = 0.020), then samples from the
   solver's root strategy for our hand. Fallback to Tier 3's river on any exception, < 20 iterations, or a missing
   piece. The endgame lock still comes first.
3. **Timing:** add `river_budget_s` to `TimingConfig`. Confirm that the hard deadline (max(80 ms, 6 × budget)) is never
   reached by the box; if it can be, raise the hard limit for river decisions only, within `hard_cap_s` and the
   per-reply rule. New `tests/test_river_timing.py` (slow): 400 hands / 60 s and 1000 / 150 s at 2× slower, vs
   calling_station and trapper, with the flag on: README rule 3's timing ratio (≤ 1.4 × Tier 3 flag-off), deadline hits ≤ the flag-off baseline +
   2√baseline.
4. **Sensitivity:** on 200 river spots, the solver's EV with our range flattened vs built. If it changes by > 20 % of
   the pot, write that our range is the weak point (RC reads gate R with that caveat).
5. Smoke run: `tier3:{"t3_river_solver":true}` vs conv_opp3 and trapper, 8 pairs, `--report stats` (iterations per
   decision, fallbacks). Not a gate.
6. Fast suite and the new slow test green, push, handoff.

## Done when
- `docs/tier4/handoff/RB.md`: the flag, the time box, iterations per decision in the smoke run, fallback rate, timing
  numbers, the sensitivity result, the commit.
