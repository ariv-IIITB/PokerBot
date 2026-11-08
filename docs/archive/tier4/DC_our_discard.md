# DC: our discard (Sonnet, cloud)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/TIER4_PLAN.md` §D3–D4, handoffs `DA.md` and `DB.md`,
and `bot/sim/discard.py` (`choose_discard`). Branch `tier4/d`: merge `origin/tier4/d-learn` into it first.
Files: `bot/sim/discard.py`, `bot/sim/inference.py`, `bot/config/tier3.json`, `tests/test_discard_*.py`, `docs/reports/TIER4_DISCARD.md`.
Seeds 21500+. `--processes` per README rule 3.

## Tasks
0. **The 2-rule opponent discard model DB found** (DB's handoff: `opponent_keeps` + `keep_straight_draw` explain 83–94 %
   of the training bots' discards, vs 75–87 % for `opponent_keeps` alone). Build it: a per-type mixture weight
   (fitted on S0's seeds 9000–9005, scored on 9006–9011), behind a param `discard_mix_model`, used both in inference's
   discard likelihood (`bot/sim/inference.py`) and as the simulated opponent's keep in `choose_discard`. Gate: the
   log-likelihood of their shown turn hand on 9006–9011 better by > 2 SE, then a sequential two-part KEEP vs `tier3`
   with DA's values, then a fresh-seed confirmation.
1. **Their keep rule in our discard:** if DB kept `discard_rule_model`, `choose_discard` lets the simulated opponent keep
   by the learned rule (else `opponent_keeps`, as now). Behind a param; A/B vs `tier3` (with DA's values), 50 pairs,
   two-part KEEP, then a fresh-seed confirmation. Skip if DB's part 2 didn't run or was dropped.
2. **Discard budget:** `special_budget_frac` (currently 0.8 of the decision budget) upward (0.8 / 1.5 / 3 / 5) until the
   README's combined timing ratio reaches 1.35 or the gain stops. Measure in
   `lab.eval` (two-part KEEP, 50 pairs), not `lab.discard_bench` (no betting, no ranges). Check timing at 2× for
   each: the discard counts toward the bank. Keep the best value whose gain is > 1 SE over the next cheaper one.
3. **Signal (only for bots DB found reacting to our discard):** among discards within `hide_margin` of the best,
   choose by the signal we want (high card thrown when we plan to bet, low when we plan to check-call). Behind a
   param; A/B against those bots only, 50 pairs. Skip if no bot reacted.
4. Write kept values to `bot/config/tier3.json`, regenerate `bot/embedded.py`, record everything in
   `docs/reports/TIER4_DISCARD.md`. Fast suite and `-m slow tests/test_timing_slow.py` green, push, handoff.

## Done when
- `docs/tier4/handoff/DC.md`: per task KEEP / DROP / skipped, with numbers, the final `tier3.json` contents, timing at
  2×, the commit. This is the D stream's final note for I1.
