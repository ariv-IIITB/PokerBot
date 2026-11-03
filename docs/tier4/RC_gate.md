# RC: gate R and the restricted river (Sonnet for the gate; Opus if you build the restricted part)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/TIER4_PLAN.md` §R (restricted, accounting, gate R),
handoffs `RA.md`, `RB.md`, `S0.md`. Branch `tier4/r`. Files: the R row of the README's ownership table. Seeds 30000+.
`--processes` per README rule 3.

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
3. **Restricted river (RNR), only if gate R passed and time allows** (slip rule: this goes first). A hidden coin makes
   the opponent the model player with probability p, otherwise a free player solved by CFR+. The model player's per-hand
   P(fold / call / each size) comes from `inference.py`'s bet model (logits γ × (strength − pivot)), with a pivot and
   γ per X2 type fitted on S0's recordings (9000–9005, scored on 9006–9011) and embedded via `tools.embed_data`.
   p = 0.5 × the family posterior mass. Param `t3_river_rnr`, default off. A/B vs the plain solver: head-to-head
   100 pairs + two-part KEEP, fresh-seed confirmation.
4. On a PASS, set `t3_river_solver` on (and `t3_river_rnr` if it passed) in Tier 3's `DEFAULTS`, regenerate
   `bot/embedded.py`. Record everything in `docs/reports/TIER4_RIVER.md`. Fast suite and slow timing green, push.

## Done when
- `docs/tier4/handoff/RC.md`: gate R PASS/FAIL per item with numbers; the restricted part KEEP / DROP / skipped; final
  flag defaults; the commit. This is the R stream's final note for I1.
