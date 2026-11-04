# DC handoff: our discard on top of DA + DB (opponent keep model, online learning, budget)

**DROP (all levers).** Nothing ships; `bot/config/tier3.json` and `bot/embedded.py` are unchanged. The code is in, default off. Branch `tier4/dc` (also `origin/tier4/dc`).
Report: `docs/reports/TIER4_DISCARD.md` (DC section); logs, drivers `logs/dc/`.
Machine: 14 cores (`nproc` 14), Intel Core Ultra 5 225H, load 6-9 from other sessions, evals `nice -n 15 flock -s`, `--processes 3`, timing under `flock -x`.

**Numbers** (30 pairs per point, seeds 21000-21029, locks off, difference of chips/hand summed over the pool, ± SE; every point flat)
- Keep-model likelihood gate (held-out half, nats/decision, mix minus softmax): passes for every bot, e.g. starter +0.81 ± 0.03, d_new_minraise +0.27 ± 0.02, d_new_rules +0.15 ± 0.02, d_conv_opp3 +0.03 ± 0.02.
- 2-rule mix (`discard_mix` / `discard_eps`) descent: best neighbour +0.54 ± 1.20, final point -0.95 ± 1.18 vs base. Left at 0.
- Online keep-rule learner (`discard_learn`): -0.34 ± 1.22 on train+tier1+tier2, -0.08 ± 0.69 on starter+calling_station. Posterior moves right (drop_lowest vs starter, opponent_keeps vs d_new_rules).
- More worlds per discard: 1.5/8000 -1.64 ± 1.18; 2.5/12000 -0.02 ± 1.16. (`discard_max_samples` 4000 was binding, so `special_budget_frac` alone did nothing.)
- No 50-pair KEEP run: no point cleared 1 SE (go/no-go says no).

**Timing** (corrected, `lab.timing_bench`, exclusive lock, 2 reps x 3 opponents, bank used per 400 hands): tier3 7.35 s; smart off 7.46 s => **DA ratio 0.99**; 1.5/8000 8.23 s (1.12x); 2.5/12000 9.75 s (1.33x); discard_learn 7.37 s (1.00x). 5/32000 is about 5.5x.
**Caveat:** `lab.timing_bench` ignored JSON brain configs until my fix (`lab/timing_bench.py`, `NAME:{json}`, commit 6010062 on `origin/tier4/dc-timingfix`); DA's 0.98/1.036 ratios came from the old tool.

**Files touched outside the D stream:** `bot/brains/tier1.py` (DEFAULTS + Opponent inference dict pass `discard_mix`, `discard_eps`, `discard_learn`, `discard_max_samples`), `lab/timing_bench.py`. Also `bot/sim/discard.py`, `bot/sim/inference.py`, `tests/test_discard_mix.py` (5 tests).
**Tests:** fast suite 1312 passed, 2 skipped (`-n 4`, after merging tier4/int). Slow suite not run.

**Not tested:** choosing our keep for post-discard play (equity vs their likely range after their discard); the manager's lever 3.
Merged `origin/tier4/int` 683bd1a. Commit: see `git log -1 tier4/dc`.
