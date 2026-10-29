# Status (updated 2026-10-29, after Phase D)

Read this after `CLAUDE.md` to know where the project stands. Plan: `docs/PART4_PLAN.md`.
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
| **E** Tier 2 on the real game (discard, tables, oppstats, bluff-catch, EV sizing) | done on `claude/phase-e-on-refactor-c07yie`, awaiting review; **upload #2 = `dist/upload2_phaseE.zip`** | see git log |
| F LLM opponent pool · G Tier 3 "Ivey" · H Problem Statement / freeze | to do | — |

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
- **Phase F:** the user is generating Discard Hold'em LLM bots (the prompt is in the plan, Phase F)
  into `Opps/discard/<model>/bot.py` and picks 2 held-out bots before seeing results.
- **Phase G:** Tier 3 ("Ivey") builds on Phase E's Tier 2. On the river, the bluff index decides
  calls, not MDF.
- **1 Nov:** the Problem Statement comes out → Phase H checks (showdown rule, provisional limits).

## Environment

- Repo: `/home/fioriv/synergy/PokerBot`, GitHub `ariv-IIITB/PokerBot`, branch `main`.
- Python 3.11 via uv: `.venv/bin/python -m pytest -n auto` (system python is 3.12; don't use it for tests).
- `Opps/opp1..opp4`: the Hold'em LLM bots (lab only, never copy into `bot/`). `opp4` used to be a
  symlink to `opp 4`; it is a real folder now.
