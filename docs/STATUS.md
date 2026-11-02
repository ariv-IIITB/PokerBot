# Status (updated 2026-11-01, CFR build map: X0, C0, X1 done; G8 re-checked)

Read this after `CLAUDE.md` to know where the project stands. Plan: `docs/PART4_PLAN.md`, and from
31 Oct **`docs/CFR_BUILDMAP.md`** (Track X exploit layer, Track C CFR; supersedes `docs/CFR_PLAN.md`).
Rules: `docs/rules/` (`SUMMARY.md` first).

## Where we are

| Phase | State | Commit |
|---|---|---|
| Rules into `docs/rules/` + docs update | done | `565da46`, `46ec387` |
| Part 4 plan (`docs/PART4_PLAN.md`) | done | `04d5a62` |
| **A** framework (scenario/transcript/round-trip kits, sandbox guard, embed generator, `lab.eval`) | done | `d3146b1` |
| **B** Discard Hold'em rules (`discard_holdem` spec is active, BB counts as a raise, fallback discard) | done, reviewed | `a44e234`, logs `57ed850` |
| **C** real protocol adapter (`bot/protocols/pokerbots.py`, now the default) | done, reviewed in D1 | `d131932`, `dd51c98` |
| **D** ship-safe → first upload | done; **upload #1 = `dist/upload1_phaseD.zip`** (the user uploads) | `accb344` |
| **E** Tier 2 on the real game (discard, tables, oppstats, bluff-catch, EV sizing) | done and merged; F0 investigation (Tier 2 vs Tier 1) done; **latest upload = #3, `dist/upload3_phaseF0.zip`** (#2 lacked its tables) | see git log |
| **F v2** Discard Hold'em opponent pool: 9 bots in `Opps/discard/` (2 converted, 7 independent), health OK | pool + health done; **held-out split chosen 2026-10-30: `d_conv_opp4`, `d_new_eqrandom`, `d_new_geometric`** (`lab/opps/discard_pool.json`); Tier 2 baseline in `docs/reports/TIER3.md`; E re-check not run | `4f72a86` |
| **G** Tier 3 "Ivey" (`bot/brains/tier3.py`) | **done; G8 passed, `tier3` is the default brain; upload candidate #4 = `dist/upload4_phaseG.zip`** (the user uploads), see `docs/reports/TIER3.md` | see git log (`phase G`) |
| Build map X0 recorder + profile table + fixtures (`docs/reports/TRACK_X.md`) | done, merged | `05d4aab` |
| Build map C0 abstraction v1 contract + reference tree (`docs/cfr/ABSTRACTION_V1.md`, `docs/reports/TIER4.md`) | done, merged | `3296194` |
| Build map X1 trait detectors (`bot/strategy/traits.py`, observe only) | done on `x/exploit-layer`, not merged | `ac6de87` |
| G8 re-check of the fixed Tier 3 | **passed** (see below); upload candidate #5 | this update |
| H Problem Statement (1 Nov): filed, no rule changed, showdown = best 5 of 7 confirmed, worked examples 8.1–8.6 as tests (`tests/test_problem_statement.py`) | done (the final freeze, 13–15 Nov, is still to do) | see git log |

Tests on Python 3.11 (`.venv`): fast suite 1063 passed, 2 skipped; slow suite 267 passed (21 min with
`-n 3`) at Phase D (`accb344`). The runtime sandbox test passes (no xfail left).

## How the work is done

- The phases are implemented by a **Sonnet** session working from GitHub. It only sees what is
  pushed. **Push `main` after every phase**, or the next session works on stale files (this already
  happened once: Phase A was built without `docs/rules/`).
- One phase per session, then stop for the user's OK. Phase work goes on a branch, then is merged
  into `main` and pushed.
- Review each phase report against the code. The Phase B report missed one flaky test (now fixed).

## Architecture refactor (2026-10-29, branch `refactor/architecture`)

Seven changes from an architecture review, one commit each, play unchanged (Tier 2 vs Tier 1 with
sample caps binding gives the same chips as before): legacy `GameConfig` retired (specs only);
`bot/artifacts.py`; the CFR abstraction moved to `bot/abstraction.py` with one showdown rule;
`messages_for` as the one visibility rule plus `HIDDEN_CHOICE`; one `Opponent` module;
`bot/situation.py` under the brains. Bug fixed on the way: `lab.harness --variant X` without
`--hands` crashed, and `--subprocess --variant X` played the embedded variant.
**Phase E continues on `claude/phase-e-on-refactor`** (the WIP ported onto the refactor; see `docs/PHASE_E_HANDOFF.md`). Load-sensitive tests can
still fail under `-n auto` on this laptop (timing-bench, Tier 1 vs random); they pass on rerun.
The package timing check is borderline on this laptop **with or without the refactor**
(projected 42–61 % of the bank vs the 50 % limit; it was well under at Phase D): Phase E has to
look at it.

## Findings so far

- **Tier 2's main leak is river showdowns** (it loses big pots and wins small ones). This was seen in
  Hold'em vs opp3 (`logs/accounting_tier2_vs_opp3_10pairs.txt`: −1.23 bb/hand, river showdowns
  −106 bb/100 net, preflop only −2) and again on `discard_holdem` vs opp3/opp4.
  So "defend wider / call down more" (MDF) can make it worse. Tier 3 must keep river
  bluff-catching tight until the opponent's bluff index says otherwise.
- **`discard_holdem` baseline** (8 pairs, 400 hands, locks off; `logs/discard_holdem_tier2_vs_bots.txt`):
  Tier 2 beats tier0, the sparring bots, opp1 and opp2. It loses to opp3 (−0.53 chips/hand) and opp4
  (−2.05). The opp bots were built for 2 hole cards and play through a makeshift adapter, so these
  numbers are indicative only; Phase F replaces them with real Discard Hold'em LLM bots.
- **Time** (fixed in D): Tier 2 now uses ~22–24 % of the bank (projected 44–49 % on a 2× slower
  server; limit 50 %) with ~5.5 decisions per hand. Every E/G change must re-pass `tests/test_timing_slow.py`.
- Tier 2 is **not deterministic run to run** (its sample counts depend on wall-clock time), so equal
  seeds don't give equal chips. Compare with enough pairs and SEs.

## Phase F0 (2026-10-29): Tier 2 vs Tier 1 investigated

Report: `docs/reports/TIER2_VS_TIER1.md`. The E7 loss to Tier 1 was partly noise (−0.64 at 50 pairs, −0.10/−0.22 at 100/60
pairs on other seeds). The one extra that cost chips, `aggr_call_shift` (call lighter vs aggressive opponents), is now
**off** (+0.64 ± 0.29 vs tier1, +0.55 ± 0.24 vs opp4, confirmed on fresh seeds; costs 4 chips/hand vs maniac, which
we beat 100 % anyway). E4 stays (turning it off is worse). **Packaging bug:** upload #2 had no embedded tables; the
builder now refuses without `data/<variant>/`; use upload #3.
`data/discard_holdem/` is committed (135 KB). If you change the variant or the precompute settings, rebuild it with
`lab.precompute --variant discard_holdem --samples 6000 --range-top 0.3`, then run `tools.embed_data`, and commit both.

## 31 Oct: book, Tier 3 fix, packaging fix, CFR build map

- `docs/book/pokerbot_book.html`: the offline two-chapter book (concepts; the repo; opponent profiles of 21 bots;
  the exploit-layer design; designs A vs B).
- Tier 3 fix `ba5800f`: a hard deadline between building the preflop model and the own-range helper silently
  turned Tier 3 into Tier 2 postflop for the rest of the match. Upload candidate #4 predates it: rebuild.
- Packaging fix: `tools.package_submission` now defaults to `bot.main.DEFAULT_BRAIN` (it defaulted to tier2 while
  main.py said tier3, so the documented command built a bot that fell back to Tier 0; the checks caught it).
- **Next: `docs/CFR_BUILDMAP.md`** (Track X exploit layer on Tier 3, ships regardless; Track C CFR with a kill gate
  on 6 Nov). It supersedes `docs/CFR_PLAN.md`.

## 1 Nov: decisions after build-map day 0, and the G8 re-check

Decisions (the user, 31 Oct evening, on `HANDOFF_2026-10-31_X0_C0.md`):

1. **X0 and C0 merged into `main`** (`46d42aa`; fast suite 1203 passed, 2 skipped) and pushed.
2. **Sized-raise cap stays 3 for CFR run 1**; drop to 2 only if C3 measures < 20k it/s (`ABSTRACTION_V1.md` §8).
3. **Removed the tracked `opps -> Opps` symlink** (nothing used it; on macOS's case-insensitive disk it
   replaced `Opps/`) (`70d4c4a`). **Book fixed** (`3d96f2f`): the column "bets river when checked to" is
   "bets river when not facing a bet" (leads included), with "… only after our check" next to it in both
   profile tables and the bot explorer (re-measured on 12 pairs; held-out bots not re-recorded).
4. **G8 re-check of the fixed Tier 3** (all G8 numbers predated `ba5800f`): fresh seeds, locks on, one eval at
   a time, no held-out pool (`docs/reports/TIER3.md`, "G8 re-check"; `logs/g/recheck/`):
   - head-to-head vs Tier 2, 100 pairs: **0.600 ± 0.035** (2.9 SE above 0.5; G8 had 0.670 ± 0.033);
   - training pool, 50 pairs, `--compare` tier2 → tier3: **KEEP**, sum +2.06 ± 0.62, no bot down (worst
     d_new_rules −0.12 ± 0.23); conv_opp3 +1.07 ± 0.35, trapper +0.62 ± 0.21; mean match score 0.59 vs 0.51;
   - `t3_errors` 0 everywhere; `t3_fallbacks` 3–14 % of decisions = the deliberate hand-offs to Tier 2.
   **Tier 3 passes again**; these are X1/X3's baseline numbers. Package rebuilt with the fix:
   **upload candidate #5** (`docs/SUBMISSIONS.md`); #4 predates the fix.
5. **Order from here:** Phase H as soon as the Problem Statement is out (priority over everything), then
   X2/X3 (Track X) and C1/C2 (Track C).

New tooling: `lab.eval --report stats` (sums each brain's own `stats` counters, e.g. Tier 3's
`t3_fallbacks`); `tools/g_eval/recheck.sh`; `lab.opps.record` / `lab.opps.traits` (X0).
Branches: `x/exploit-layer` (X1 on top of `70d4c4a`), `cfr/tier4` (C1/C2 in progress).

## Open items for the next phases

The plan was finalized on 2026-10-29 (`docs/PART4_PLAN.md`): done phases are marked, and every
phase starts by reviewing the previous one.

- **Phase D (done):** see the "Done" box in `docs/PART4_PLAN.md`. Upload #1 is
  `dist/upload1_phaseD.zip` (sha256 in `docs/SUBMISSIONS.md`); the user uploads it on Unstop.
- **Phase E:** Tier 2 gets the lessons from the Hold'em LLM bots: an `oppstats` module, a
  **river bluff index** (aimed at the river leak), **EV bet sizing**, and no awkward leftovers.
  Each is kept only on the numbers. Upload #2.
- **CFR (Tier 4), decided 2026-10-29:** a separate track, `docs/CFR_PLAN.md`. K1–K3 (abstraction,
  trainers, river solver) are lab work and can run in their own session alongside E–G. Gate A
  (blueprint vs Tier 2 and opp3) ~3–4 Nov; if it fails, Tier 3 ships.
- **Phase F (v2, replaces the plan above):** the pool was built here, not by the user: `Opps/discard/*`
  (conv_opp3, conv_opp4 + 7 independent sub-agent bots), registered as `d_<name>`, all pass
  `lab.pool_health`. **Still to do, in this order:** the user picks the held-out split (before any result),
  then the Tier 2 baseline and the Phase E re-check (`tools/f_eval/run_f2.sh`). Until then nobody has read
  a Tier 2 chip result against a pool bot, and G must not tune on any pool bot.
- **Phase G (done, 2026-10-30):** Tier 3 = Tier 2 + the style (preflop tables from the 3-card
  classes, texture c-bets, MDF defence with floats, polarised barrels, river value/bluff ratios,
  capped adaptation), plus `eq_floor` and a gated `value_floor`. Facing a river bet stays Tier 2's
  bluff-index rule. G8 passed: vs Tier 2 locks on 0.670 ± 0.033; training pool locks on +1.57 ± 0.54
  (mean match score 0.62 vs 0.55); held-out +1.16 ± 0.50. **Default brain = `tier3`.**
- **Biggest open problem:** both brains lose chips to d_conv_opp3, d_new_rules, d_new_exploiter and
  d_new_geometric, at river showdowns. Next work goes there (train pool only).
- **1 Nov:** the Problem Statement comes out → Phase H checks (showdown rule, provisional limits).

## Environment

- Repo: `/home/fioriv/synergy/PokerBot`, GitHub `ariv-IIITB/PokerBot`, branch `main`. A Mac copy at
  `~/Desktop/pokerbots_synergy2` is also used (local branch `master` tracks `origin/main`).
- Numba (`numba==0.62.1`, lab only) is in `requirements-dev.txt` for the CFR trainer: re-run
  `uv pip install --python .venv/bin/python -r requirements-dev.txt`.
- Python 3.11 via uv: `.venv/bin/python -m pytest -n auto` (system python is 3.12; don't use it for tests).
- `Opps/opp1..opp4`: the Hold'em LLM bots (lab only, never copy into `bot/`). `opp4` used to be a
  symlink to `opp 4`; it is a real folder now.
