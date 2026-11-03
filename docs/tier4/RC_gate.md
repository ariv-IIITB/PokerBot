# RC: gate R and the restricted river (Sonnet for the gate; Opus if you build the restricted part)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/TIER4_PLAN.md` §R (restricted, accounting, gate R),
handoffs `RA.md`, `RA2.md`, `RB.md`, `S0.md`. Branch `tier4/r`. Files: the R row of the README's ownership table. Seeds 30000+.
`--processes` per README rule 3.

## Step 0
Merge RA2's branch (named in `handoff/RA2.md`) into RB's branch. RA2 kept `solve_river`'s API, so this should be
clean; run the fast suite and RA's bench once after the merge.

## Tasks
1. **Accounting SE:** extend `lab/opps/accounting.py` (or `lab.eval --report accounting`) to report each bucket's
   chips/hand with an SE over pairs, and a combined "all river buckets" line (showdown + we fold + they fold).
   Test it on a small run.
2. **Gate R** with the time box halved (`river_budget_s` 0.010, standing in for the 2× server):
   `tier3:{"t3_river_solver":true}` vs `tier3`:
   - head-to-head 100 pairs, score ≥ 0.5 − 2 SE;
   - training pool two-part KEEP;
   - the combined river buckets vs conv_opp3 and exploiter better by > 2 SE (not showdown alone, which folding more
     can game);
   - timing: RB's slow test passes.
   If RB's sensitivity check flagged our range, state that caveat next to the result.
3. **Restricted river (RNR), required** (its own gate decides KEEP/DROP; the slip rule drops it first only if the deadline gets close). A hidden coin makes
   the opponent the model player with probability p, otherwise a free player solved by CFR+. The model player's per-hand
   P(fold / call / each size) comes from `inference.py`'s bet model (logits γ × (strength − pivot)), with a pivot and
   γ per X2 type fitted on S0's recordings (9000–9005, scored on 9006–9011) and embedded via `tools.embed_data`.
   p = 0.5 × the family posterior mass. Param `t3_river_rnr`, default off. A/B vs the plain solver: head-to-head
   100 pairs + two-part KEEP, fresh-seed confirmation.
4. On a PASS, set `t3_river_solver` on (and `t3_river_rnr` if it passed) in Tier 3's `DEFAULTS`, regenerate
   `bot/embedded.py`. Record everything in `docs/reports/TIER4_RIVER.md`. Fast suite and slow timing green, push.

5. **Hard-limit margin (user-approved 2026-11-04; run after the gate evals finish, never edit `bot/` while they run).** Shipped
   config, unloaded, 2× clock harness, exclusive lock: wall time of every river decision (p50/p99/max) against its hard limit
   (`TimeManager.hard_limit`: min(max(0.08, 6 × budget), 1.5 s, 0.3 × reply, 0.25 × bank_left)). Require max ≤ 0.5 × the limit;
   if not, raise the hard limit for river decisions within the existing caps.
6. **Middle fallback rung.** Today `Controller.choose` (`bot/main.py`) falls to Tier 0 (check, else FOLD) on a hard-deadline hit,
   an escaped exception or emergency mode; hard-deadline warnings do occur under CPU load (seen in the gate logs). On DeadlineExceeded
   or a brain Exception (not emergency): retry once with `brain.decide(state, legal, 0.0)` under a ~30 ms hard deadline, then Tier 0.
   First confirm Tier 3 at budget 0 skips rollouts and the solver and returns a legal sensible action in < 10 ms; if not, report that
   and build nothing. Counter `deadline_retries` in the stats line. Tests: deadline → retry used; retry also fails → Tier 0;
   emergency → Tier 0 directly; nothing ever raises out of `choose`. Fast suite once, one timing ratio check.

## Done when
- `docs/tier4/handoff/RC.md`: gate R PASS/FAIL per item with numbers; the restricted part KEEP / DROP / skipped; final
  flag defaults; the commit. This is the R stream's final note for I1.
