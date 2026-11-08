# Handoff after Phase E (2026-10-29)

> **Correction (Phase F0):** upload #2 was built without the embedded tables and is superseded by upload #3
> (`dist/upload3_phaseF0.zip`, sha `38705aa4…`). `aggr_call_shift` is now 0. See `docs/reports/TIER2_VS_TIER1.md`.

Phase E is merged into `main` (`f9a858a`). Read `CLAUDE.md`, `docs/STATUS.md`, `docs/PART4_PLAN.md` first.
Upload #2 is `dist/upload2_phaseE.zip` (sha256 `1baec44f…`, 113 KB). `dist/` is not in git: rebuild with
`.venv/bin/python -m tools.package_submission --zip --stage2`.

## What is implemented (Tier 2 on Discard Hold'em)

| Step | State | Where |
|---|---|---|
| E1 fast sampled one-card discard (`discard_mode="fast"`) | **on** | `bot/sim/discard.py`, `lab/discard_bench.py` |
| Smart discards inside rollouts (`smart_rollout_discard`) | built, **off** (loses ~1.3 ± 0.4 vs tier1) | `bot/sim/rollout.py` |
| E2 embedded preflop/discard tables | **on** | `bot/embedded.py` (generated; `data/` is gitignored) |
| `table_range_weight` | built, **off** (0.5 lost 2.8 vs maniac) | `bot/situation.py` |
| E3 opponent stats (bluff index, fold rates by street and size) | on, feeds E4 | `bot/strategy/oppstats.py` |
| E4 river bluff-catch (`river_bluff_slope` 0.5) | **on** (default) | `bot/brains/tier2.py` |
| E5 `ev_sizing` | built, **off** (lost 1.9 vs tight, ~4 SE) | `bot/brains/tier2.py` |
| E6 `leftover_frac` | built, **off** (no gain) | `bot/brains/tier2.py` |
| Pacing `safety_factor` 4.5 → 5.5 | on | `bot/timing.py` |
| Tools | `tools/e_eval/run_e.sh`, `summ.py`, `head2head.py` | |

All keep/drop numbers are in `docs/reports/TIER2_DISCARD.md`; E7 logs are in `logs/e7/`.

## Results

Core pool, 30 pairs, chips/hand ± SE (base = current defaults before E4):
base vs tier1 −0.06 ± 0.27, opp3 −0.08 ± 0.10, opp4 −1.35 ± 0.33. With E4: tier1 +0.08 ± 0.38, opp3 +0.01 ± 0.11,
opp4 −0.65 ± 0.23, nothing else worse by more than 2 SE.

**E7, final bot, full pool, 50 pairs, 400 hands** (match score in brackets):

| Opponent | chips/hand | score |
|---|---|---|
| random_legal | +22.53 ± 0.37 | 1.00 |
| all_in | +23.07 ± 0.49 | 1.00 |
| maniac | +51.86 ± 0.52 | 1.00 |
| calling_station | +8.61 ± 0.11 | 1.00 |
| tight | +8.16 ± 0.26 | 1.00 |
| starter | +7.52 ± 0.10 | 1.00 |
| opp1 | +7.69 ± 0.22 | 0.99 |
| opp2 | +2.58 ± 0.19 | 0.89 |
| opp3 | +0.10 ± 0.07 | 0.61 |
| **tier1** | **−0.64 ± 0.24** | **0.38** |
| **opp4** | **−0.60 ± 0.17** | **0.38** |

Head-to-head, current Tier 2 vs the Phase D config, 50 pairs: **+0.68 ± 0.26**, score 0.54.

Timing, package checks on the final zip (projected at a 2× slower server, limit 50 %): 37–48 %; peak RSS ~39 MB.
Fast suite 1096 passed, 2 skipped; `tests/test_timing_slow.py` 6 passed.

## Issues and what we are dealing with

1. **Tier 2 loses to tier1 (score 0.38) and opp4 (0.38) in the full-pool run.** The plan said Tier 2 must beat
   tier1. At 30 pairs tier1 was a draw, so part of this may be noise, but 50 pairs gives −0.64 ± 0.24 (~2.7 SE).
   Tier1 itself changed in Phase E (it plays the discard too), so "vs tier1" is not comparable to Phase D numbers.
   Not yet investigated: run `lab.opps.accounting`-style reports (`--report accounting,profile` output is in
   `logs/e7/full.txt`) on tier1 and opp4. The known leak is river showdowns.
2. **E4's gain is small** (opp4 +0.7 ± 0.4) and measured at 30 pairs only.
3. **Timing is close to the limit.** The first package build failed at 51–57 %. Raising `safety_factor` to 5.5 fixed
   it (worst case 48 %). Any new per-decision cost needs `lab.timing_bench` and `tests/test_timing_slow.py` again.
4. **`python -m tools.embed_data` needs `data/discard_holdem/`**, which is gitignored. Run in a fresh container
   it writes a 3.8 KB `bot/embedded.py` without the tables and breaks two tests. Do not commit that output;
   rebuild the tables first (`lab.precompute --variant discard_holdem --samples 6000 --range-top 0.3`, ~3 min).
   `bot/embedded.py` on `main` is correct.
5. **Flaky under load:** `tests/test_tier1.py::test_tier1_beats_random_and_plays_legally` can fail under `-n 4`
   and passes alone. Evals are wall-clock based, so runs are not reproducible; compare configs at the same time.
6. opp1–opp4 are Hold'em bots on a makeshift adapter; indicative only until Phase F.
7. E1/E2 were decided in an earlier session (its commits were lost with the container); only their end state is
   on `main`, not the raw numbers beyond the table in `docs/PHASE_E_HANDOFF.md`.

## Open decisions for the user

- Upload #2 now, or investigate the tier1/opp4 losses first?
- Start the CFR track (`docs/CFR_PLAN.md`)? Not started.

## Next

F (LLM opponent pool, held-out split) · G (Tier 3) · H (1 Nov Problem Statement, final freeze). Deadline 15 Nov 2026, 23:59 IST.
