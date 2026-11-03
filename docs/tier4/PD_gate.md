# PD: gate P (Sonnet, ~1–1.5 days, mostly compute)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/TIER4_PLAN.md` "Gate P", handoffs `PA.md`, `PB.md`,
`PC.md`, `S0.md`. Branch `tier4/p`: merge `origin/tier4/p-tune` and `origin/tier4/p-sel` into it first (they touch
different parts of `tier4p.py`; if they conflict, keep PB's values and PC's code). Seeds 12000+. `--processes 3`.

The incumbent is the one PA named (`tier3x` if gate X passed, else `tier3`).

## Gate P (all must pass)
1. **Detection, offline:** on S0's recordings (seeds 9000–9011, never used to build `types.json`), replay the posterior
   and selection hand by hand. Over hands 200–400, the right member plays ≥ 70 % of hands against each training and
   sparring bot, and `base` plays ≥ 90 % against random_legal and all_in.
2. **Each member vs Tier 3**, forced on: 50 pairs head-to-head, not worse than −0.10 chips/hand and score ≥ 0.5 − 2 SE.
3. **vs the incumbent:** head-to-head 100 pairs, score ≥ 0.5 − 2 SE. Training pool, two-part KEEP (locks off for chips,
   locks on for score, `lab/opps/score_compare.py`). Where a member differs from what `tier3x` does (PB's tuned values,
   `anti_aggro` vs lag), that bot must be up by > 2 SE; elsewhere, not down.
4. **Live detection:** in the locks-off pool run, `--report stats`: the right member plays ≥ 70 % of hands 200–400.
5. **Adversary:** 50 pairs vs `adversary`: lose no more than the incumbent does + 2 SE.
6. **Stage 2:** one 1000-hand pool run (30 pairs, `--hands 1000`), incumbent on the same seeds, two-part KEEP.
7. **Timing and size:** add `tier4p` cases to `tests/test_timing_slow.py` (400 hands / 60 s and 1000 / 150 s at 2×
   slower, vs calling_station and trapper). ≤ 50 % of the bank; deadline hits ≤ the Tier 3 baseline + 2√baseline over
   the same hands. `.venv/bin/python -m lab.memory_check --variant discard_holdem` < 500 MB.
   `.venv/bin/python -m tools.package_submission --zip --stage2 --brain tier4p` passes.

Run the comparisons with both arms back to back. Record every number in `docs/reports/TIER4P.md`.

## Done when
- `docs/tier4/handoff/PD.md`: **PASS or FAIL** for each of the 7 items, with numbers. On PASS, the package's sha256
  (an upload candidate; don't upload, the user does). On FAIL: which item failed, and the statement that I1 ships the
  incumbent.
