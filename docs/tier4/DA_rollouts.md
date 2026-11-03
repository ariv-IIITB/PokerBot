# DA: flop equity with real discards (Sonnet, ~1 day, mostly compute)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/TIER4_PLAN.md` §D intro and D1,
`docs/reports/TIER2_DISCARD.md` (the Phase E smart-rollout result). Branch `tier4/d` from `origin/tier4/base`.
Files: `bot/config/tier3.json` (new), `bot/sim/rollout.py` (only if the timing needs a fix), `docs/reports/TIER4_DISCARD.md`,
tests. Seeds 20000+. `--processes 3`.

**The gap:** flop equity rollouts discard **at random for both players** (`smart_rollout_discard` is off by default,
`bot/brains/tier1.py:51`; `bot/sim/rollout.py` `rollout_policy`). So every flop bet/call decision misjudges hand
value. Phase E turned smart rollouts off because they lost 1.3 ± 0.4 vs tier1 (Tier 2, 30 pairs). Hypothesis to test:
the thresholds were tuned on random-discard equity.

## Tasks
1. **Cost first:** time Tier 3 decisions with `smart_rollout_discard` on vs off (`lab.timing_bench` or `--report stats`).
   If the bank use at 2× would pass 50 %, stop and write the handoff.
2. **(a) On, no retune:** `tier3:{"smart_rollout_discard":true}` vs `tier3`, training pool + tier1 + tier2, 30 pairs,
   locks off and on.
3. **(b) On + retune:** a 3 × 3 grid on `raise_equity` (shift all streets by −0.04 / 0 / +0.04) × `call_margin`
   (−0.02 / 0 / +0.02), 30 pairs per point, same pool.
4. **Confirm** the best of (a) and (b) on fresh seeds: 50 pairs, two-part KEEP vs `tier3`.
5. On KEEP: write the values to a new `bot/config/tier3.json` (check how `tools/embed_data.py` picks up
   `bot/config/*.json`, and that `load_params("tier3", ...)` then sees them), regenerate `bot/embedded.py`, and add a
   test that the embedded tier3 params carry the new values. On DROP: change nothing in `bot/`.
6. Record every result, kept or dropped, in `docs/reports/TIER4_DISCARD.md`.
7. Fast suite green, `-m slow tests/test_timing_slow.py` green, push, handoff.

## Done when
- `docs/tier4/handoff/DA.md`: KEEP or DROP with numbers (± SE, pairs), the timing cost, the values set, the commit.
