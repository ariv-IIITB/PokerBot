# DA handoff: smart rollouts on Tier 3 + retune

**KEEP.** Branch `tier4/d` (pushed from worktree branch `claude/d-f73be4`). Report: `docs/reports/TIER4_DISCARD.md`; logs, driver `logs/da/`.
Machine: 14 cores (`nproc` 14), Intel(R) Core(TM) Ultra 5 225H, load average 25-30 from other sessions, evals at `nice -n 15`, 3-6 processes.

**Values set** (`bot/config/tier3.json`, embedded): `smart_rollout_discard: true`, `raise_equity: [0.70, 0.68, 0.68, 0.74]` (only the turn entry moved, 0.70 -> 0.68),
`call_margin` stays 0.02. `tier3x` and any brain with `param_file = "tier3"` inherit this.

**Numbers**
- Cost, locked, unloaded: smart on / off = 1.036 (48.49 s vs 46.79 s, 6 matches). Final check, new tier3 vs old tier3: 0.98 (43.01 vs 43.77 s). Limit 1.4.
- Deadline hits: no "hard deadline" warning in either timing file (harness may not show the bot's stderr). In the loaded tuning logs the smart-OFF
  reference had 185 and the smart-on start 27: the hits follow load, not the flag, so no cap was added to `bot/sim/rollout.py`
  (`logs/da/deadline_hits.txt`; per 1000 decisions about n/864).
- Tuning (30 pairs, seeds 53000+, each ± about 1.2): smart-on default vs plain +0.72 ± 1.26; round 1 move `re[2]` 0.70 -> 0.68 (+1.47 ± 1.24);
  round 2 and the 3 x 3 grid (`re[0]` x `re[2]`): every neighbour worse (-0.8 ... -2.2), no further move. Winner's curse is likely in the one move.
- Confirmation, 50 fresh pairs (seeds 54000+), new tier3 vs old plain tier3: chips locks off sum **+2.33 ± 0.88 (z +2.7)**, no bot down > 2 SE
  (lag +0.96 ± 0.44, others within ± 0.45); score locks on **+0.006 ± 0.022** (0.641 -> 0.648). Two-part KEEP. No Stage 2 run, no sequential extension (light-testing rule).
- Not separated: smart rollouts alone vs the `re[2]` change; they ship together.

**Tests:** fast suite 1291 passed, 2 skipped (`-n 4`); slow suite not run (manager's rule). `tests/test_tier3.py` gained the values test; its Tier 2 equality test now skips keys `tier3.json` sets.

**For DC:** build on this branch; `bot/sim/rollout.py` and `bot/sim/discard.py` are untouched. The baseline to beat is now the new tier3 (smart on).
**For I1:** merge `bot/config/tier3.json` + the regenerated `bot/embedded.py` (regenerate with `.venv/bin/python -m tools.embed_data`, never hand-merge).
Commit: see `git log -1` on `tier4/d`.
