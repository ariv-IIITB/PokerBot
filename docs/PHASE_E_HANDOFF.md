# Phase E handoff (written 2026-10-29)

Phase D is done and on `main` (`c3a3201`, upload #1 = `dist/upload1_phaseD.zip`, sha256 `2dab3f52…`,
see `docs/SUBMISSIONS.md`). Phase E is partly built.

**Update 2026-10-29 (later): work on branch `claude/phase-e-on-refactor`, not
`claude/eager-sagan-tn3syo`.** `main` got an architecture refactor (see `docs/STATUS.md`,
`GLOSSARY.md`), and the WIP was ported onto it with identical play (Tier 2 vs Tier 1 with sample
caps binding: same chips as the old branch). Where things moved:
- the per-spot stats are `brain.opponent.spots` (an `OppStats` inside `bot/opponent.Opponent`, fed
  by `Opponent.observe`), not `brain.stats` (that name clashed with the CFR brain's diagnostics);
- discard mode, the rules' fallback discard, `smart_rollout_discard` and `table_range_weight` live
  in `bot/situation.py` (`Situation.special`, `Perception`); tables are `brain.perception.tables`;
  equity is `brain.situation(state).equity(budget)`;
- embedded tables are `ARTIFACTS["tables"]` (`bot/artifacts.py`); `data/discard_holdem/` was
  rebuilt from the branch's embedded copy;
- `test_redraw` passes: it was a wall-clock flake (now capped by worlds), not the tables or discard. Read `CLAUDE.md`, `docs/STATUS.md`, `docs/PART4_PLAN.md` (Phase E) first. Rules: never
copy from `Opps/`; tests green on Python 3.11 (`.venv`); if three fixes in a row fail, stop and report.
Setup: `uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt`.

## What is already built on the branch (flags decide what is active)

| Step | Code | State |
|---|---|---|
| E1 discard | `bot/sim/discard.py` (sampled one-card discard, `discard_mode="fast"`), smart discards inside rollouts (`bot/sim/rollout.py`, `smart_rollout_discard`), `lab/discard_bench.py` (offline decision quality), tests `tests/test_discard_fast.py` | Fast discard is on and good. Smart rollouts are **off by default** (see results). |
| E2 tables | `data/discard_holdem/` made by `lab.precompute --variant discard_holdem --samples 6000 --range-top 0.3` (3 min), embedded by `python -m tools.embed_data` into `bot/embedded.py` (185 KB). `data/` is gitignored; only `bot/embedded.py` is committed. `table_range_weight` (blend the vs-top-range table when facing a preflop raise) is coded, default 0. | Embedded. Tables were computed with smart rollouts. |
| E3 oppstats | `bot/strategy/oppstats.py`, `tests/test_oppstats.py` (prior 15 obs, gate 20, cap ±0.15; spots: bluff_index, fold_flop/turn/river, fold_small/mid/big) | Done, fed by `Tier2Brain.observe`. |
| E4 bluff-catch | `Tier2Brain.adjusted(street)`: `call_margin += river_bluff_slope * (bluff_ref - bluff_index)` from the turn on | Coded, `river_bluff_slope` **default 0 (off)**, unmeasured. |
| E5 EV sizing | `Tier2Brain.ev_size`, flag `ev_sizing` (default off) | Coded, unmeasured. |
| E6 leftovers | `Tier2Brain.no_leftovers`, `leftover_frac` (default 0 = off; try 0.25) | Coded, unmeasured. |
| E9 | note added to `docs/PART3_ROADMAP.md` | Done. Ask the user about CFR in the report; do not start it. |

Known problem when I stopped: the full fast suite had **1 failure, `tests/test_redraw.py::test_default_policy_redraws_a_dangerous_card`**
(1088 passed). Not yet diagnosed: probably the new tables or the fast discard changing a default policy
in a redraw variant (`use_tables` / `discard_mode` in that test's brain). Fix or pin the test's config first.
Also: `docs/reports/TIER2_DISCARD.md` is only a header; the table below must go into it.

## Measurement method (the keep rule)

Keep a step only if the pool aggregate improves and no opponent drops by more than 2 SE
(`lab.eval --compare`). Because Tier 2 plays ~22 hands/s per core, I used the **core pool**
`tier1 calling_station tight maniac starter opp3 opp4`, **30 pairs**, locks off, `--variant discard_holdem`,
and ran before/after configs at the same time on one machine (budgets are wall-clock, so load matters).
Tools: `tools/e_eval/run_e.sh SNAPSHOT NAME 'tier2:{json}' PAIRS PROCS [opponents...]` and
`tools/e_eval/summ.py SNAPSHOT/logs/e` (summary table). Run from a **frozen copy of the repo**
(`tar` without `.venv/.git/dist/logs`), so edits don't leak into running jobs. Machine had 4 cores:
one process per config. The plan's full pool (12 opponents, 50 pairs) is only for the final E7 check.
Use `--report accounting` to read river-showdown losses vs opp3/opp4 for E4.

Config names used (`tier2:{...}`; the opponent `tier1` always runs the current defaults):
- **D baseline:** `{"discard_mode":"pimc","smart_rollout_discard":false,"use_tables":false,"river_bluff_slope":0.0}`
- **E1:** `{"use_tables":false,"river_bluff_slope":0.0}` with smart rollouts ON (set `"smart_rollout_discard":true`; the default is now false)
- **E1 fast-only:** `{"smart_rollout_discard":false,"use_tables":false,"river_bluff_slope":0.0}`
- **E1+E2:** E1 with tables on.

## Results so far (chips/hand ± SE, match score in brackets; 30 pairs)

| | tier1 | calling_station | tight | maniac | starter | opp3 | opp4 |
|---|---|---|---|---|---|---|---|
| D baseline | +0.76±0.28 (0.60) | +7.47±0.12 | +8.23±0.41 | +51.29±0.55 | +6.48±0.11 | −0.19±0.11 (0.43) | not run |
| E1 (fast + smart rollouts) | −0.56±0.31 (0.43) | +10.74±0.17 | +8.83±0.32 | +50.07±0.72 | +9.40±0.18 | +0.27±0.10 (0.63) | not run |
| E1 fast discard only | +0.50±0.31 (0.57) | +7.79±0.11 | +8.39±0.32 | not run | not run | not run | not run |
| E1+E2 (tables) | −0.82±0.32 (0.37) | +10.36±0.16 | +9.16±0.35 | +53.47±0.71 | +9.33±0.15 | +0.12±0.07 (0.59) | −1.01±0.32 (0.35) |

Offline discard benchmark (`python -m lab.discard_bench --deals 3000 --seed 11 --budget-ms 5`, share of pot
over the "lowest card" fallback): fast +0.052–0.062, PIMC +0.053, old PIMC (random rollouts) +0.044–0.052,
keep-two-highest +0.01. fast beats old PIMC by +0.007..+0.009 ± 0.003 (paired). So the sampled discard
beats the simple discards by a wide margin and the old PIMC by ~3 SE.

Reading: smart rollouts give ~+3 chips/hand vs calling_station and starter but lose ~1.3 ± 0.4 vs tier1
(a drop by the keep rule), so they are off. Fast-only has no regression so far. Tables look neutral to
slightly positive except opp4 (needs the D and fast-only opp4 numbers to judge).

## Still to do

1. ~~Fix the `test_redraw` failure; commit the WIP~~ (done on `claude/phase-e-on-refactor`).
2. Finish the missing runs: opp4 for D, E1 and fast-only; maniac, starter, opp3, opp4 for fast-only. (Jobs were
   killed by a worker restart; relaunch only the missing opponents.) Decide E1: likely **keep fast discard,
   drop smart rollouts** unless a retune fixes the tier1 loss (try `raise_equity` +0.04 with smart rollouts).
3. E2: compare tables vs no tables with fast-only as base (and `table_range_weight` 0.5). Keep rule.
4. E4: base + `river_bluff_slope` 0.5; use `--report accounting` on opp3/opp4: river showdown losses must shrink
   without losing more to folds. E5: `ev_sizing` true. E6: `leftover_frac` 0.25. Each against the kept base,
   same time, same seeds. Record **every** result, kept or dropped, in `docs/reports/TIER2_DISCARD.md`.
5. E7: `lab.sparring_audit --variants discard_holdem`, then `lab.eval tier2 --pool` full E pool
   (`tier1 random_legal calling_station tight maniac all_in starter opp1 opp2 opp3 opp4`) `--pairs 50 --locks off
   --report accounting,profile`. Tier 2 must beat tier1, every sparring bot and the starter; report opp1–4 with the
   Hold'em-bot caveat.
6. E8: re-run `lab.timing_bench` (400 and 1000 hands, vs tier2-nolock, maniac, starter) and
   `pytest -m slow tests/test_timing_slow.py`; Phase D limits: projected 2× ≤ 50 % of the bank, reply ≤ 0.5 s. Embedded tables and
   oppstats add little per decision, but check.
7. E10: if Tier 2 improved, set the kept defaults (in `DEFAULTS` and `bot/config/tier2.json`), regenerate
   `bot/embedded.py` (`python -m tools.embed_data`), run `python -m tools.package_submission --zip --stage2`,
   record the hash in `docs/SUBMISSIONS.md`, hand the zip to the user (upload #2).
8. Merge into `main`, push `main`, update `docs/STATUS.md` and the Phase E "Done" box in `docs/PART4_PLAN.md`,
   report to the user (include the CFR question from E9), then stop for review.
