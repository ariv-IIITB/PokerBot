# Tier 4 manager state (handover from the first Tier 4 manager, 2026-11-04 evening)

You are the Tier 4 manager now. Read `CLAUDE.md`, `docs/tier4/README.md` (rules every session follows, seed blocks, laptop lock
rules) and `docs/tier4/MANAGER.md` (older, partly stale: this file replaces its "State now" and "Redo list").

## Mandate (the user's words, now signed off for the night)
Make the bot **optimal, as good as possible**. Time is not an object. Decide for yourself, do not ask the user for things, do the
manager's job end to end: start and steer sub-plan sessions, verify every handoff (branch, base, numbers) before acting, chain the
next step, integrate what is proven, remove what is not. Keep a plain running log in `docs/tier4/MANAGER_LOG.md` (what finished, what it
decided, what is next; short) and push it, so the user can read it when back. Message the user in chat only for a meaningful gain.
Still not yours to do without the user's explicit OK in chat: upload anything, merge into `main`, `git push --force`, delete branches,
anything outside this repo. Prepare everything (final package, `docs/SUBMISSIONS.md` note) and leave those steps for the user.
Sub-sessions: Sonnet by default (the user's standing instruction); Opus only for real design work.

## Integration rule (user)
Pieces go into `tier4/int` when their testing is complete and above noise; later work is tested **on top of `tier4/int`**, not on plain
Tier 3. A piece that does not hold up in the stack is removed again (the user: "then we will see whether to remove it or not"). Use
`git revert` for removals, never force-push. Run the fast suite before every push (`.venv/bin/python -m pytest -n auto`).
Chips matter most (net chips over 400 hands); simple bots may lose some chips as long as the match score vs each stays > 0.5; never
hardcode to bot names or constants (general adaptive rules). The `Opps/` bots are ours: reading and reusing them is allowed.

## What is in `tier4/int` now (origin/tier4/int, fast suite 1295 passed)
- tier4/base (= `tier3x`: Tier 3 + exploit layer X1-X3, the incumbent).
- DA: smart discard rollouts + retuned `raise_equity` in `bot/config/tier3.json` (50 pairs chips +2.33 +- 0.88; time x0.99).
- O3 arm B ON by default: `x_narrow` True, `x_air_eq` 0.45 (`bot/brains/exploit.py`, `tier3x.py`). The user said to put it in. Cloud 100-pair
  confirmation (locks off, `origin/tier4/o3-cloud`, logs/o3c/): sum +4.17 +- 0.47 (conv_opp3 -1.37 -> -0.03, exploiter +1.06, minraise +0.54,
  trapper +2.26, lag -1.03 +- 0.34 = flagged by the strict rule, but we still win +5.24/hand vs lag, score was 0.86). Still pending from that
  cloud session (it cannot message; read its branch): locks-on scores, simple-bot guard, the single blind `d_new_rules` run, arm A. Note:
  arm A (`x_narrow` only) lost less vs lag in screening: switch to it if the stack check says x_air_eq hurts lag.
- Tooling fix: `lab/timing_bench.py` passes `NAME:{json}` configs to the bot (the old version silently timed plain tier3).

## Sessions running (ids for SendMessage; each sends you its reports; ask them to message you, the notes otherwise go to the first manager)
- DC `local_d15d542f-de9e-4e63-ba85-18ad71cbf2fc` (discard: rule learner `discard_learn`, budget 2.5/12000 = x1.33 time; 30-pair evals running).
- AD `local_43a12aac-c095-4a09-b67f-fcf6a4530db3` (faster adaptation; round 1 trust/push arms: exploiter +0.08/+0.14 noise, other bots running).
- RF `local_57bcdd79-e689-4498-81f8-fa0784b9d81e` (diagnose and fix the CFR river + RNR; first step also measures solver coverage).
- PS `local_80b76483-f8bf-4f76-9340-336d5f424ef0` (portfolio `tier4p` on top of O3 vs `tier3x` on int: the user's check "tier 4 + O3 on top"; keep or remove it on evidence).
- O3 cloud session (user-started, no messaging; branch `origin/tier4/o3-cloud`).
- Local O3 `local_87f9ba4a-...` is stopped on purpose (its work is on `origin/tier4/o3`, 76bbc2f). Archive it when convenient.

## Decided: rejected or parked (do not redo without a new reason)
- PF preflop chart: no-go (lever flat within noise). MW match-win layer: no-go. GX gate X redo: cancelled.
- River solver + RNR (RD, RC): no gain over Tier 3 on our pool (h2h 0.540 +- 0.050, chips +0.42 +- 0.48), flag `t3_river_solver` OFF. **The user wants it kept
  as a ship candidate** (principled vs strong balanced bots): RF is trying to fix it; I1 decides it on held-out/blind bots with "no worse than the stack without it".
  RC's fallback fix (`Controller.choose` retries Tier 3 at budget 0) is on `origin/tier4/r`, not yet in int: merge it (safety).
- Portfolio `tier4p` (PD): strict gate-P fail (anti_value score 0.405 +- 0.035 vs floor 0.43); gains only on weak bots; PS re-tests it on top of O3.
- O3 arm C (`x_stab`) dropped (hurt lag). DB: no single discard rule, no bot reacts to our discard; `discard_mix`/`discard_eps` flat.

## Open leads and ideas (queue them yourself)
- After PS: keep or remove `tier4p`. After DC/AD/RF: merge confirmed pieces, then re-run the stack.
- Exploit layer gaps (TRACK_X): station, preflop-folder and trapper moves not built. 3-bet pots we call lose ~19 chips/pot vs conv_opp3 and exploiter (postflop):
  per-street accounting (`lab.opps.accounting`) is the next study.
- Blind set 2: the user has Gemini build nine bots from `docs/tier4/BLIND2_PROMPTS.md`; when they appear in `Opps/discard_blind2/<name>/bot.py`, register a `blind2` pool
  (final-only, like the held-out set) and run it once at the end. Held-out bots (conv_opp4, eqrandom, geometric): only I1, once, with `--final`.
- I1 (`docs/tier4/I1_integrate.md`): final merge and checks incl. the stacking-order test (add pieces one at a time, 30-pair training runs), combined timing, memory,
  fuzz, head to head 100 pairs, Stage 2, held-out once, package (`tools.package_submission --zip --stage2 --brain <chosen>`). Default if nothing passes: `tier3x`/`tier3`.
  Package it and write the hash in `docs/SUBMISSIONS.md`; the user uploads.

## Mechanics you must know
- Monitor: `python3 tools/tier4_monitor.py`; sessions: `list_sessions {"linked": true}` (only sessions you start are linked to you).
- `start_session` is refused on automated turns (heartbeats, side-session events); on those you can only SendMessage existing sessions, `unarchive_session`, or
  propose cards (`own_initiative`). Start new sessions in turns that a user message or your own first turn begins, and batch what you need.
  Cloud sessions cannot message back and send no notes; local only, except where noted.
- Laptop (14 cores, shared; the bots' time budgets are wall-clock so oversubscription spoils results): evals as
  `flock /tmp/pokerbot_turnstile.lock true; nice -n 15 flock -s /tmp/pokerbot_laptop.lock <cmd>`, `--processes 3`, ONE lab.eval per bot so the lock frees between jobs;
  timing as `flock /tmp/pokerbot_turnstile.lock flock -x /tmp/pokerbot_laptop.lock <cmd>` (plain `flock -x` starves behind shared jobs). Both arms of a comparison back to back.
  Numbers from different machines are never compared. Never leave a background waiter whose command matches its own pgrep.
- Timing is a hard limit: the new brain <= 1.4 x Tier 3's bank use, 0 extra deadline hits; ship decisions need bigger runs (100 pairs) than tuning points (30).
- Archive finished sessions with `archive_session` only after you verified their handoff branch; delete is irreversible (needs a card).
- Branch names: local sessions can use the plan names (`tier4/<x>`); `source_branch` must be a local branch (`git update-ref refs/heads/<b> origin/<b>`).
- Seed blocks (README): RF 73000s, PS 74000s, AD 72000s, O3 71000s, RD 70000s; new sessions take the next free thousand.

## Heartbeat
Create a cron (CronCreate) every 3 hours with this prompt: "Tier 4 manager heartbeat: run `python3 tools/tier4_monitor.py` and `list_sessions {"linked": true}`. If every
linked session is working and no handoff is new, do nothing and say nothing. If a session is idle/stalled (e.g. after a usage limit, or its background jobs are gone),
SendMessage it to continue; if a handoff is new, verify branch/base/numbers and act per this file." Sessions that sit idle with no running jobs (check
`/proc/<pid>/cwd` of lab.eval processes per worktree) have stalled: nudge them.
