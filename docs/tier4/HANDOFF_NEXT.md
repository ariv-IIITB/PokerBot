# Handoff for the next chat (written 2026-11-06 by the retired Tier 4 manager; read this first)

Repo `/home/fioriv/synergy/PokerBot`, branch `tier4/int` (origin/tier4/int = the integration branch and the bot that would ship). Never upload, merge into `main`,
force-push or delete branches without the user's explicit OK in chat. Chips matter most; simple bots may lose chips if the match score vs each stays > 0.5; no hardcoding to bot names.
The user wants the bot as good as possible; time is not an object. Tokens are limited: keep replies short.

## Read, in order
1. `docs/rules/RULE_CHANGES_2026-11-06.md` (NEW RULES: two legs of 200 hands, fresh process per leg, 30 s bank per leg; new PDFs are in `docs/rules/`).
2. `docs/tier4/MANAGER_STATE.md` and `docs/tier4/MANAGER_LOG.md` (mandate, rules for sessions, laptop lock rules, seeds), `CLAUDE.md`, `docs/tier4/README.md`.

## What the bot is
`bot.main.DEFAULT_BRAIN = "tier3x"` (set 2026-11-05; before that the packager would have shipped plain tier3). tier3x = Tier 3 + exploit layer X1-X3 + DA's discard tuning
(`bot/config/tier3.json`) + O3 arm B (`x_narrow` on, `x_air_eq` 0.45) + RF's CFR river with RNR (D4, on in tier3x) + RC's budget-0 retry + H1 `x_def` 0.5 (on, UNCONFIRMED).
Rejected: preflop chart, match-win layer, portfolio `tier4p` (flat on top of O3), O3 arm C, discard levers (flat). Brain names: "Tier 4" is the project, the brain is `tier3x`.

## Stopped / paused (everything below was in progress and needs a restart)
1. **Repo not yet updated for the new rules (do first):** `variant/catalog/discard_holdem.json` and `variant/active.json` still say 400 hands / 60 s: set 200 hands / 30 s (a leg), run
   `.venv/bin/python -m tools.embed_data`, check `tools/package_submission.py` smoke checks, `lab/timing_bench.py` and `tests/test_timing_slow.py` use the leg format,
   update `docs/rules/SUMMARY.md` and the hard-constraint lines of `CLAUDE.md` (they still say 60 s/400 hands, one process per match). Fast suite after.
2. **Starter kit with `engine.py`:** the user said they would upload it; it did NOT arrive (only the three PDFs). Ask for it. Then run the packaged bot through the real engine
   for a full two-leg Stage 1 match (the true final check) and compare with our lab's behaviour.
3. **Final check vs all bots, in the new format** (killed after 5 of 16 at the old 400-hand format; those 5 are in `logs/final/old400/`: conv_opp3 -0.56 score .650; exploiter -0.26 .662;
   lag +0.12 .975; rules -0.13 .762; trapper +0.61 .912; 40 pairs, locks on). Rerun with `--hands 200 --bank 30`, ~80 pairs, brain `tier3x`: training bots, simple bots
   (calling_station tight maniac random_legal all_in starter tier1), held-out (d_conv_opp4 d_new_eqrandom d_new_geometric, `--final`; released for study by the user), then plain
   `tier3` on the nine LLM bots for the comparison. Driver `logs/final/run.sh` (edit hands/bank/pairs; it runs on a frozen worktree `.claude/worktrees/final-check`, recreate with
   `git worktree add --detach .claude/worktrees/final-check HEAD` at the commit you want to test).
4. **H1 (`x_def`) 100-pair confirmation** (never completed; the cloud session H1 is paused): `tier3x` vs `tier3x:{"x_def":0}`, fresh seeds 81000+, locks off for chips, locks on for score,
   at 200-hand legs use 150-200 pairs. Script `logs/final/h1conf.sh`. Revert H1 (default `x_def` 0 in `bot/brains/exploit.py`) if the sum is not clearly up.
5. **Adaptation is the main risk of the new rules:** the bot sees 200 hands then restarts. AD's baseline: the read was at full strength by hand ~100 vs exploiter and ~300 vs conv_opp3,
   so vs the slow-to-read bots the exploit layer barely acts in a leg. Ideas (unmeasured): (a) feed preflop stats (200 observations per leg) into the opponent-family posterior;
   (b) embed priors from our recordings (`logs/records/s0_9000`, 12 bots) so fewer observations are needed (the only way to carry knowledge between legs);
   (c) retune `x_ramp` (20), the 0.8 posterior and 60-observation gates for 200 hands; (d) chips per hand by hand number for the first 50 hands of a leg.
   Re-measure the whole stack at `--hands 200` before trusting any 400-hand number.
6. **Manager session `mgr2`** (`local_cbf0c50f-5533-416e-ba2c-76253848f38c`, Opus) is idle and holds until the user says continue; it created a 3-hourly heartbeat. Cloud sessions H1 and the
   O3 cloud session cannot message back; read their branches `origin/tier4/h1`, `origin/tier4/o3-cloud`. Other sessions are idle (AD paused by the user).
7. **I1 (final integration, held-out run, package, `docs/SUBMISSIONS.md` hash)** waits for the usage reset ~8 Nov (user decision). Build: `.venv/bin/python -m tools.package_submission --zip --stage2`
   (default brain tier3x). Timing recheck on the laptop first: the cloud box showed tier3x at x1.38-1.58 of tier3, RF measured x1.17-1.36 on the laptop; the limit is 1.4 and a hard
   50 % of the bank at 2x slower. Use `lab/rc_ratio.py` plus the fixed `lab.timing_bench` (configs reach the bot via `$POKERBOT_BRAIN_CONFIG`).
8. **Minor:** river solver hardcodes 52 cards (`bot/strategy/river_solver.py:225,364-375,757`; not live for Discard Hold'em); duplicated percentile and size-rank code in `tier3.py`/`tier3x.py`;
   second blind set (9 bots from `docs/tier4/BLIND2_PROMPTS.md`) not built; `/ultrareview` free runs: 1 of 3 used.

## Remote play (done)
`lab/remote_seat.py`, `lab/remote_relay.py`, opponent name `remote:PORT` in `lab/eval.py`, `docs/REMOTE_PLAY.md` (includes the message for friends). Tested on localhost only.
Use a bigger `--bank` for remote matches (network delay is charged to the friend's bank).

## Laptop rules (shared machine; bot budgets are wall-clock)
Evals: `flock /tmp/pokerbot_turnstile.lock true; nice -n 15 flock -s /tmp/pokerbot_laptop.lock <cmd>`, `--processes 3`, one `lab.eval` per bot. Timing: `flock /tmp/pokerbot_turnstile.lock flock -x /tmp/pokerbot_laptop.lock <cmd>`.
Both arms of a comparison back to back; never compare numbers across machines; do not use broad `pkill -f` (the auto-mode classifier blocks it): kill by pid.
