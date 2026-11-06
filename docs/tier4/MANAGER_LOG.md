# Tier 4 manager log

(2026-11-04 evening) Manager handed over. State: docs/tier4/MANAGER_STATE.md. tier4/int = base + DA + O3 arm B on. Running: DC, AD, RF, PS, O3 cloud.

(2026-11-04 night, new manager) Heartbeat cron 3-hourly created. DC/AD/RF/PS told to report to me.
- Merged origin/tier4/r into tier4/int (RC's budget-0 retry fallback in Controller.choose + river solver code, flag t3_river_solver OFF, so tier3x behaviour unchanged). Fast suite 1345 passed (one tier1 test flaked once under laptop load, passes alone).
- O3 cloud (100 pairs, locks off, arm B vs base): sum +4.17 +- 0.47, lag -1.03 +- 0.34 (still +5.24/hand). Arm B stays on (user decision); arm A is the fallback if the stack check says x_air_eq hurts lag.
- The app refuses start_session in the manager's turns (no user words here): new work goes to existing idle sessions via SendMessage, or to own_initiative cards.
- O3C (arm B confirmation on int: locks-on scores, simple-bot guard, arm A vs B, blind d_new_rules once, timing) given to the local O3 session (seeds 74000+), handoff docs/tier4/handoff/O3C.md, branch tier4/o3c.
- L3 (3-bet-pot leak study, seeds 75000+) proposed as a card (task_8292d771); needs the user's click.
- Open: PS (tier4p on top of O3) handoff, DC, AD, RF status; then merge DC/AD pieces; RF river fix; blind2 pool; I1.
- AD status: branch claude/ad-fe9a68 on int 0ca4a45, round 1 trust/push arms vs exploiter noise-level (+0.08/+0.14); ETA round 1 ~3-4 h, then round 2, 50-pair confirmation, timing, handoff.
- DC status: all discard levers flat at 30 pairs (best -0.95+-1.18, learner -0.34+-1.22, budget 2.5/12000 -0.02+-1.16): DROP, defaults off. Asked for DC.md handoff, then lever 3 (keep choice for post-discard play), no-go if flat.
- PS status: tier4p rebuilt on Tier3XBrain (inherits O3), gate running (5 bots, 50 pairs, seeds 74000 locks off/on, h2h 74500); ETA hours. NOTE seed clash: PS uses 74000 and O3C (my brief) also 74000: tell O3 to use 76000+.
- DC handoff verified (origin/tier4/dc 2ee9627, DC.md): all levers DROP, flat within 1.2 SE. NOT merged into int (default-off code with no gain). Lever 3 requested.
- 2026-11-04 18:59 User paused everything (laptop closing). Stopped DC and RF turns; O3/AD/PS were idle. Background evals left as-is: suspend freezes them and Python's perf_counter (CLOCK_MONOTONIC) excludes suspend time, so budgets stay valid. On resume: check each session's jobs, nudge to continue.
- RF status (arrived after the pause, its turn stopped again): solver loses on face_big (conv -0.97, exploiter -0.62, trapper -0.51 river chips/hand) and under-bets first-to-act vs over-folders/stations; narrowing reaches 0.58 top-30% mass vs truth 0.7-1.0. Candidates C1 sharp narrow, C2 +strong RNR, C3 +face_base hybrid queued; then coverage.
- 2026-11-04 21:07 Resumed after the user's pause. The laptop had rebooted: every background job was gone. Told PS, RF, AD, O3 (O3C) and DC (lever 3) to rerun cut-off runs from scratch and continue.
- 2026-11-04 21:42 O3 cloud (origin/tier4/o3-cloud) finished: arm B locks-on 100 pairs score 0.682->0.805 (+0.123+-0.018, KEEP-score; lag 0.990->0.975); simple-bot guard 1.000 vs all six; blind d_new_rules -0.25->+0.22 chips, 0.44->0.57 score (generalised). Arm B CONFIRMED. Local O3C cut to arm A vs B + timing. Cloud is doing the 3-bet accounting (lab.opps.threebet_acct).
- 2026-11-04 21:56 L3 started by the user (local_cdf9d0d3; told to rebase onto origin/tier4/int, reuse the cloud's threebet_acct). Head-to-head tier4/int vs main tier3: user said don't run it; only a 1-pair smoke test ran (works: scratchpad h2h.py, int as `bot.main --brain tier3x` subprocess vs main bot.py). NOTE: int's DEFAULT_BRAIN is still "tier3": the package must pass --brain tier3x (I1).
- 2026-11-04 23:46 DC lever 3 (discard_stake) flat: stake1 -0.60+-1.26, stake2 -1.42+-1.33 -> no-go; DC wraps up. PS at locks-on runs; O3 arm A run; RF candidate runs; AD round 1; L3 building x_3b_ref (tight-3-bettor continue cap, off) on int.
- DC handoff addendum verified (origin/tier4/dc ee9f16e). DC done; not merged (all levers DROP). Archive DC when the user agrees.
- 2026-11-04 23:55 USER DECISION: drop the portfolio tier4p (flat on top of O3: locks-off sum ~0, lag -0.45). PS told to stop and write a short handoff. USER DECISION: I1 (final merge and checks) waits until after the weekly usage reset (2026-11-08 ~09:30 IST); weekly limit was 75% used at 2026-11-04 ~midnight. Until then: AD, RF, O3 (arm A + timing), L3 finish their pieces; merges into tier4/int still happen as handoffs land.
- PS handoff verified (origin/tier4/ps, PS.md): DROP, sum -0.02 +- ~0.54. PS done.
- O3C handoff verified (origin/tier4/o3c c21122a): arm B vs base +4.33+-0.62 (lag -0.70+-0.45), arm A +3.34 (lag -1.10, fails), B vs A +0.99+-0.56. Timing tier3x/tier3 1.05-1.10 (limit 1.4). DECISION: arm B stays in tier4/int. O3 done.
- 2026-11-05 02:00 After user reboot #2 (RF was in confirm.sh: D4 = solver + sharp narrowing + RNR vs BASE, 50 pairs seeds 73100, 20 runs, 1 done). Resumed RF (rerun from the cut-off run) and L3; AD stays paused.
- 2026-11-05 03:21 RF status: D4 (solver + narrow n0 0.001 + one-sided RNR vs callers) vs tier4/int, 50 pairs 73100 locks off: sum +1.94+-0.57 (lag +1.78 z4.0, minraise +0.40, trapper -0.32 -1.7SE) chips KEEP; timing x1.17-1.36, 0 hits; coverage 100%. Locks-on run ~2h, then RF.md.
- 2026-11-05 04:16 L3 handoff verified (origin/tier4/l3 e99d5cc, on int): cause = we continue ~90% vs 3-bets (eq_floor vs random hand). x_3b_ref R10 KEEP formally but noise: locks-off +0.56+-0.54, score -0.002+-0.024, guard 1.000, timing x1.00. DECISION: not merged (flag stays off; no gain). L3 done. RF confirm finished, asked for RF.md.
- 2026-11-05 04:18 RF handoff verified (origin/tier4/rf d7f0313, on int): D4 KEEP. MERGED into tier4/int and switched on in tier3x defaults (plain tier3 unchanged); embed regenerated; fast suite 1351 passed; smoke vs calling_station: 185 solves, 0 errors/fallbacks. tier4/int now = tier3x + DA + O3 arm B + RC retry + RF D4. Next: I1 after the usage reset (2026-11-08); AD paused.
- 2026-11-05 10:13 USER: skip AD. Held-out bots released for study; new blind set coming. Requested cloud session H1 (task_82525173, branch tier4/h1, seeds 77000+): tier3x vs held-out baseline, O3-style mechanisms, general adaptive fixes, KEEP on held-out + training + score + guard + timing. Cloud: read origin/tier4/h1, no messages.
- 2026-11-05 10:56 /ultrareview items: fixed (1) deadline-split river caches, (3)(4) docstrings, (7) CLAUDE.md safety text; skipped (2) 52-card constant (not live), (5)(6) cosmetic. Timing finding for I1 written in MANAGER_STATE (timing_bench x2 projection overstates the solver; use rc_ratio, add tier3x to test_timing_slow).
- 2026-11-06 (new manager, taking over after the retired one's handoff) Read HANDOFF_NEXT/RULE_CHANGES/MANAGER_STATE/MANAGER_LOG/README/starter_kit. New rules (two legs of
  200/500 hands, 30s/75s bank per leg, fresh process per leg) confirmed (RULE_CHANGES_2026-11-06.md, starter_kit/README.md).
- Step 1 done, pushed (434026d): variant/active.json + the discard_holdem catalog to 200 hands/30s; embed_data, package_submission's --stage2 check (500h/75s),
  lab.timing_bench docstrings, tests/test_timing_slow.py + test_river_timing.py (slow) to the leg sizes; SUMMARY.md + CLAUDE.md hard-constraint lines rewritten for two
  fresh-process legs (also: files may now be read inside the bot's own submission). Fast suite 1359 passed; slow timing/river tests green at the new sizes.
  Found + fixed in passing: spec_hash() hashed match.hands/time_bank_s, so the hands=400->200 edit invalidated every precomputed artifact (equity tables, opponent type
  library) though match length can't affect card equity; excluded those two fields and patched the stale spec_hash in data/discard_holdem/{meta,types}.json. Caught because
  a first embed_data run silently dropped ARTIFACTS (bot/embedded.py fell from 199 KB to 4 KB) — always check the file size/ARTIFACTS block after regenerating.
- package_submission --zip --stage2's own timing check flags tier3x vs starter 52%/51% (cap 50%): confirmed this is the already-known timing_bench linear-2x-projection
  overstatement (MANAGER_STATE "I1 timing"), not a new regression — the accurate clock_scale=2 measurement (box halved) gives ratio 1.32 vs starter, within the 1.4 limit.
  Left for I1 to fix the check's methodology (use the clock_scale-2 harness), as already planned. Not blocking.
- Step 2 done: packaged bot (dist/submission/bot.py) run through starter_kit/engine.py (the organisers' real local runner) for full two-leg matches vs
  random_bot (seed 1, +337/-337, 0.00s/0.00s used), lab's starter_bot (seed 2, +435/-435), Opps/discard/new_exploiter (seed 3, -161/+161, 2.25s/4.84s used, B wins
  — single seed, not a quality signal) and a --stage 2 (1000-hand) run vs random_bot (seed 4, +673/-673). All four: zero notices, well inside the per-leg bank and
  wall clock. "0.00s used" vs weak opponents is correct, not a bug: the whole 200-hand leg finishes inside the 5s per-leg start-up grace, so nothing gets charged.
- Found before starting the real final check: logs/final/run.sh and h1conf.sh passed no --hands/--bank, so they'd have defaulted to lab.eval's stale --hands 400
  against the active spec's new 30s bank — starved pacing, not the new rules' 200-hand leg. Fixed (f6107b1): both now pass --hands 200 --bank 30 explicitly.
  Recreated .claude/worktrees/final-check at tier4/int HEAD (db850f1; it was still pinned at 076d253, pre-rules-update).
- Step 3 launched in the background (logs/final/run.sh, nohup-equivalent): tier3x vs LLM+simple+held-out pools (40 pairs, seeds 80000+, locks on, --hands 200
  --bank 30), then plain tier3 on the 6 LLM bots for the delta. Results land under logs/final/<brain>__<opp>.txt as each finishes; logs/final/ALL_DONE when the
  whole matrix is done. Not yet looked at.
- Step 3 landed (logs/final/, 40 pairs, seeds 80000+, locks on, --hands 200 --bank 30, zero errors/forfeits everywhere): tier3x's match score vs EVERY bot in
  the pool, training + held-out + simple, stayed above 0.5 (worst: d_new_exploiter 0.575, d_conv_opp3 0.625; best: the simple bots and d_new_lag at 0.96-1.00).
  tier3x beats plain tier3 on every one of the 9 LLM bots (chips and score both up or flat; exploiter's score alone crosses 0.463 -> 0.575, i.e. tier3 loses that
  match, tier3x wins it). Current default stays a clean ship candidate under the new rules.
  BUT: comparing to the old-format partial run (logs/final/old400/, same 40 pairs/seeds, 400 hands in one process) shows the halved per-leg hand count hurts the
  bots the exploit layer is slowest to read: d_new_exploiter score .662->.575 and chips -0.26->-0.57 (worse on both), d_new_trapper .912->.800 and chips
  +0.61->+0.25 (worse), d_conv_opp3 .650->.625 and chips -0.56->-0.66 (slightly worse); d_new_lag flat (.975->.963) and d_new_rules slightly better
  (.762->.800) are not hurt. This is exactly the adaptation risk the retired manager flagged (item 5): the exploit layer needed ~100 hands vs exploiter and
  ~300 vs conv_opp3 to reach full strength in one continuous process: at 200 hands/leg it's cut short against the slow-to-read bots, especially conv_opp3's
  300-hand estimate. Not a ship blocker (score still > 0.5 everywhere) but a real, measured degradation worth fixing: re-tuning x_ramp/the posterior gates for
  200 hands (HANDOFF_NEXT idea c) is the most promising next lever, since it directly shortens the read time the exploit layer needs.
- (4) H1 (x_def) confirmation launched in the background at the new per-leg sizes (logs/final/h1conf.sh, fixed to --hands 200 --bank 30): tier3x vs
  tier3x:{"x_def":0}, chips locks-off 100 pairs then score locks-on 50 pairs, 9 bots, seeds 81000+. Will revert H1 (default x_def back to 0) if the sum isn't
  clearly up once this lands.
- (5) User asked to attack the adaptation-speed problem directly: started two parallel sub-sessions. ADT (hand-tune x_ramp/x_vo_min_obs/ALPHA-BETA directly,
  seeds 82000s) finished: **NO-GO on everything**, verified (branch claude/adt-ac9719 / tier4/adt, on tier4/int 4b3dbc3, handoff docs/tier4/handoff/ADT.md,
  fast suite green, tree clean, nothing merged). Diagnosis is the useful part: d_new_exploiter's bottleneck is a partial lambda ramp (x_ramp-fixable in
  principle, but x_ramp 8/12/5 all washed to noise at n=60); d_conv_opp3's SPRT never reaches a verdict in 60% of 200-hand legs (not fixable by nudging
  thresholds: ALPHA/BETA 0.05->0.10 only got it to 10/20 legs deciding, flat pool sum, and caused a feedback-loop side effect — looser alpha changes our own
  early play enough to reduce conv_opp3's OWN value-only (X2) convergence, 0/20 legs vs 4/20 at baseline); d_new_trapper's .912->.800 drop isn't an X1/X2
  timing problem at all (its traits/posterior already ramp fine) — needs its own diagnosis (x_narrow/x_def, or might just be the original 40-pair number's
  noise, no SE was reported for it). ADT's suggested next lever: embed priors from logs/records/s0_9000 for conv_opp3 (changes hand-0 knowledge, not
  learning speed) rather than more threshold tuning.
  AD2 (revive+generalize the abandoned "AD" length-scaling machinery, bot/strategy/adapt.py, for legs shorter than the 400-hand reference too, seeds
  83000s) is running in parallel on its own branch (tier4/ad2) — ported and passing the fast suite, not confirmed yet. Its core lever (loosening the SPRT's
  alpha/beta, via a length factor) is mechanically close to ADT's lever 3, which just came back NO-GO with that feedback-loop warning — flagged to it.
  User wants both compared, best one (or a merge of both) taken. Neither merged into tier4/int yet.
- (6) H1 confirmation landed (seeds 81000+, 200h/30s): chips (locks off, 100 pairs/bot) ON-minus-OFF sums to +0.28 chips/hand over the 9 bots, score
  (locks on, 50 pairs/bot) sums to +0.08 match-score over the 9 bots — both near zero, mixed signs (conv_opp4/lag worse on chips; conv_opp4/rules worse on
  score), nothing past 2SE either way on any single bot. Not clearly up -> **reverted H1**: `x_def` default back to 0.0 in `bot/brains/exploit.py`
  (`EXPLOIT_DEFAULTS`), `tests/test_exploit.py::test_x_def_on_by_default` renamed/flipped to `test_x_def_off_by_default`. Fast suite green (1359 passed, 2
  skipped). AD2 checked against its own baseline (n=60, seeds 83000s): `x_len_push` is non-monotonic on d_conv_opp3 (-0.23 baseline -> +0.19 at push=0.5,
  +0.16 at push=1.0, but -0.41 at push=1.5 — should get *better* with more push if the lever were real) and drifts d_new_lag/d_new_trapper slightly worse —
  classic noise signature (cf. ADT's x_ramp n=30->n=60 wash), not a real signal. **AD2 dropped**: session stopped, worktree and branch
  (claude/ad2-2976f1) deleted, nothing was merged or pushed. OVF remains the live lever for the adaptation-speed problem (principled zero-drift-SPRT fix,
  extending its own n=30 result to n=60).
- (7) **Speculative merge, user decision 2026-11-06:** ovf's combined fix (overfolder_tr, "fix 2", + X2 type-posterior bridge via x_oft_*, "fix 1")
  merged into tier4/int (69c8606/f8b33c0) ahead of its own confirmation, on the user's explicit call ("push it, we can remove it later"). Status at merge
  time: fix-2-alone n=60 was flat at the chip level (sum +0.28±0.80, z 0.35) despite a verified real decision-speed win (overfolder_tr decides 57/60 legs
  by hand 71 vs the pooled test's 42/60 by hand 99); the combined fix1+fix2 n=30 looked more promising (conv_opp3 -0.17->+0.62, pool sum +1.27±1.17) but
  is NOT YET confirmed at n=60 — that run is still in progress in ovf's own worktree (seeds 84000s). Both `x_of_tr` and `x_oft_enabled` default to True,
  so this is now live in tier4/int's default `tier3x` behaviour pending that confirmation. Fast suite green post-merge (1362 passed, 2 skipped; one
  `test_river_solver.py` timing test flaked under shared-laptop load from ovf's concurrent eval run, passed clean in isolation — not a regression).
  **Revert plan if ovf's n=60 doesn't hold up:** `git revert f8b33c0` on tier4/int (clean single merge commit, should revert cleanly since nothing else
  has touched these files since).
