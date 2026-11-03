# Tier 4 manager handoff

You are the new manager of Tier 4. The previous manager session is retired. This file is everything you need;
read it fully, then `CLAUDE.md`, then `docs/tier4/README.md`. Read sub-plans and handoff notes only when you act on them.

## The user's instruction (verbatim intent)

- **Everything as close to optimal as possible**: not "good enough", not limits the manager picked. The only limits
  are the hard ones (below). Earlier work done to a lower standard is **redone** to this standard (list below).
- **Run everything locally** on this laptop and **manage it yourself**: start the sub-plans, check their results,
  fix branch problems, chain the next steps. Don't make the user paste prompts or track tables.
- Report to the user in short, plain words: what finished, what it decided, what's next.
- The previous manager made mistakes the user is angry about: it set "fast enough" bars instead of best ones (RA),
  made quiet trade-off calls, and lost track of branch names. Don't repeat these. **Never do something you can't
  see and check.** Verify every branch, base and number yourself before acting on it.

## Hard limits (the only ones)

From `CLAUDE.md` and `docs/rules/`: Python 3.11, NumPy/SciPy only in `bot/`, no file reads at runtime, 1 vCPU / 1 GB,
**time bank 60 s per 400 hands and 150 s per ~1000 hands, ≤ 50 % used on a 2× slower server** (this laptop is the
calibration machine: `tests/test_timing_slow.py` and `lab.timing_bench` numbers on it are binding), **5 s per reply**,
5 MB zip, never crash or forfeit, and the **deadline 15 Nov 2026, 23:59 IST**. Leave time for a final check and the
user's upload. Two ideas are out because they can't work, not to save time: solving earlier streets live (no value
estimate for the depth limit) and IS-based strategy selection (no power in 400 hands; see `docs/TIER4_PLAN.md` §P).

**Actions that need the user's explicit OK in chat:** uploading anything, merging into `main`, `git push --force`,
deleting branches, anything outside this repo.

## Where things are

- Design and reasons: `docs/TIER4_PLAN.md` (v5). Sub-plans: `docs/tier4/*.md`, index `docs/tier4/README.md` (its
  "Aim" section = the optimal-within-limits rules: spend safe time up to a 1.35 × Tier 3 timing ratio, coordinate-
  descent tuning, sequential tests 30 → +30 → … until |z| ≥ 2.5 or 200 pairs, nothing optional).
- Base branch: **`tier4/base`** = `main` + Phase H + the exploit layer X1–X3 (code commit `a9fd1f3`; later commits on it
  are docs only). Every stream branches from it.
- Monitor: **`python3 tools/tier4_monitor.py`** (fetches, finds every handoff note, the branch it's on, whether the
  branch has the right bases, and what's ready). State file `.scratch/tier4_state.json` (`started` list; edit it
  when you start a sub-plan). It only reads git.
- Teammate's CFR: branch `cfr/tier4`, independent. Merging it is Tier 5. Never edit `bot/cfr/`, `lab/cfr/fast/`,
  `docs/reports/TIER4.md`. The user was given messages for the teammate (river solver and exploit layer on GitHub);
  you don't need to contact them.

## Branch naming problem (important)

Cloud sessions push to their own `claude/<random>` branch, not the plan's `tier4/*` name. The plan names are kept as
**aliases** that point at the real branch: `tier4/s0`, `tier4/p`, `tier4/r`, `tier4/d-learn` exist. After a sub-plan
finishes, check its branch is built on the right base (monitor's `missing_bases`) and fast-forward the alias to it
(`git push origin <branch>:refs/heads/<alias>`, never `--force`). Local sessions you start can use the plan names directly.

## State now

| id | status | branch | result / what it decided |
|---|---|---|---|
| S0 | done | `tier4/s0` | recordings `logs/records/s0_9000/` (12 bots × 9,600 hands, opponent cards on every hand) + `lab/opps/score_compare.py`. Fine. |
| PA | done | `tier4/p` (= `claude/tier4-pa-subplan-cwh07j`) | `tier4p` with 4 forced members; gate X **KEEP but weak** (chips +0.83 ± 0.67, score +0.042 ± 0.026, 50 pairs, cloud). Incumbent = `tier3x`. |
| RA | done | `tier4/r` (= `claude/zen-ptolemy-4w0rqi`) | solver GO only bucketed (64 buckets, pot + all-in): ~1 % of pot exploitability; exact version too slow. **Superseded by RA2.** |
| DB | done | `tier4/d-learn` (= `claude/subplan-xx-5o7o4k`) | D0: no single rule; `opponent_keeps` + `keep_straight_draw` explain 83–94 %. D4: no bot reacts to our discard. Part 2 not built (now DC task 0). |
| PB | running, cloud | `claude/elegant-tesla-012fmu` | member tuning, **trimmed one-at-a-time grid** (old standard) |
| PC | running, cloud | `claude/subplan-xx-execution-4m4kgt` | selection, bail-out, stop-loss, adversary bots |
| DA | running, cloud | `claude/tier4-da-rollout-c9wbz2` | smart rollouts + 3×3 retune grid (old standard) |
| RB | running, cloud | `claude/subplan-xx-execution-g00q9v` | solver hook in Tier 3, own range, river timing (WIP) |
| RA2 | not started | — | near-exact solver (`docs/tier4/RA2_exact.md`) |
| PD, DC, RC, I1 | not started | — | see their sub-plans (already upgraded to the optimal standard) |

The user may have pasted "update" messages into PB, DA and RB (coordinate descent, sequential tests, spend safe time,
RB not to touch the solver files). Check each branch's latest commits to see whether they did. **First decision for
you:** let the four cloud chats finish (then redo their work to the new standard where needed) or ask the user to stop
them and redo locally. They cost nothing locally; their numbers are cloud numbers (different machine): the binding
re-checks must run here.

## Redo list (done to a lower standard)

1. **Gate X (PA)**: re-run on this laptop with the sequential test (it decides the incumbent; 50 pairs was not
   significant). Members' code is fine.
2. **PB tuning**: coordinate descent to convergence + a 3 × 3 on the two most sensitive parameters, per member; at least
   `anti_folder` (biggest loss family) in full. Confirm on fresh seeds, sequential tests.
3. **DA retune**: coordinate descent over `raise_equity` per street + `call_margin` until no improvement, then 3 × 3.
4. **River time box**: not a fixed 20 ms. Spend the bank headroom (Tier 3 ~34 % at 2×, limit 50 %): raise the box until
   the combined ratio vs Tier 3 reaches 1.35, measured on this laptop. Hard deadline for river decisions raised to match
   (within `hard_cap_s` 1.5 s and 0.3 × the reply limit).
5. **RA → RA2**: the solver as close to exact as possible at every box size (RA2 sub-plan).
6. **Discard**: build DB's 2-rule model (DC task 0); discard budget raised until the 1.35 ratio or no gain.
7. **Restricted river (RNR)**: required, not optional (RC).
8. **Sample sizes**: sequential tests everywhere; Stage 2 (1000-hand) runs required.
9. **Every cloud number that decided something** (PA gate X, DA, DB, RA, PB, PC smoke) is re-checked on this laptop
   before it counts.

## Running locally

- This laptop: 14 cores. Several sessions can run at once. Rules from the earlier laptop design: `--processes` =
  floor(12 / sessions running evals), fixed per session; every `lab.eval`/`lab.opps.record` under
  `flock -s /tmp/pokerbot_laptop.lock`, every timing check under `flock -x` on the same file; both arms of a comparison
  back to back in one session; never compare numbers across machines.
- Start each sub-plan as its own local session (keeps your context small): give it its sub-plan file, the branch to
  start from, the README rules, and "write `docs/tier4/handoff/<id>.md` and push". Use cheaper models for pure
  compute runs, Opus for design. Read only their handoff notes, then verify (branch, base, numbers) yourself.
- Keep the laptop awake while sessions run (ask the user once; the app can keep it awake).

## Order from here

1. Decide what to do with the 4 running cloud chats (above).
2. Start **RA2** now (independent).
3. Redo gate X locally (it fixes the incumbent everything else compares against).
4. As each running stream finishes: verify, alias, redo to standard where needed, start the next (PD after PB+PC,
   DC after DA+DB, RC after RB+RA2, I1 after PD+DC+RC).
5. I1 picks what ships (default `tier3`, upload candidate #5, unless a candidate passes every gate). The user uploads.

Report to the user only at real decisions or results.
