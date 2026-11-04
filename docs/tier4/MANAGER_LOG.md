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
