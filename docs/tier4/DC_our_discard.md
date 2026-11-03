# DC: our discard (Sonnet, ~1 day)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/TIER4_PLAN.md` §D3–D4, handoffs `DA.md` and `DB.md`,
and `bot/sim/discard.py` (`choose_discard`). Branch `tier4/d`: merge `origin/tier4/d-learn` into it first.
Files: `bot/sim/discard.py`, `bot/config/tier3.json`, `tests/test_discard_*.py`, `docs/reports/TIER4_DISCARD.md`.
Seeds 21500+. `--processes 3`.

## Tasks
1. **Their keep rule in our discard:** if DB kept `discard_rule_model`, `choose_discard` lets the simulated opponent keep
   by the learned rule (else `opponent_keeps`, as now). Behind a param; A/B vs `tier3` (with DA's values), 50 pairs,
   two-part KEEP, then a fresh-seed confirmation. Skip if DB's part 2 didn't run or was dropped.
2. **Discard budget:** `special_budget_frac` (0.8 of the decision budget today) at 0.8 / 1.5 / 3. Measure in
   `lab.eval` (two-part KEEP, 50 pairs), not `lab.discard_bench` (no betting, no ranges). Check timing at 2× for
   each: the discard counts toward the bank. Keep the cheapest value within 1 SE of the best.
3. **Signal (only for bots DB found reacting to our discard):** among discards within `hide_margin` of the best,
   choose by the signal we want (high card thrown when we plan to bet, low when we plan to check-call). Behind a
   param; A/B against those bots only, 50 pairs. Skip if no bot reacted.
4. Write kept values to `bot/config/tier3.json`, regenerate `bot/embedded.py`, record everything in
   `docs/reports/TIER4_DISCARD.md`. Fast suite and `-m slow tests/test_timing_slow.py` green, push, handoff.

## Done when
- `docs/tier4/handoff/DC.md`: per task KEEP / DROP / skipped, with numbers, the final `tier3.json` contents, timing at
  2×, the commit. This is the D stream's final note for I1.
