# Status (updated 2026-10-29)

Read this after `CLAUDE.md` to know where the project stands. Plan: `docs/PART4_PLAN.md`.
Rules: `docs/rules/` (`SUMMARY.md` first).

## Where we are

| Phase | State | Commit |
|---|---|---|
| Rules into `docs/rules/` + docs update | done | `565da46`, `46ec387` |
| Part 4 plan (`docs/PART4_PLAN.md`) | done | `04d5a62` |
| **A** framework (scenario/transcript/round-trip kits, sandbox guard, embed generator, `lab.eval`) | done | `d3146b1` |
| **B** Discard Hold'em rules (`discard_holdem` spec is active, BB counts as a raise, fallback discard) | done, reviewed | `a44e234`, logs `57ed850` |
| **C** real protocol adapter | **next** | — |
| D ship-safe → first upload · E Tier 2 on the real game · F LLM opponent pool · G Tier 3 "Ivey" · H Problem Statement / freeze | to do | — |

Tests on Python 3.11 (`.venv`): fast suite all green (1 expected failure: the runtime sandbox test,
an xfail until Phase D). The slow suite passed at Phase B.

## How the work is done

- The phases are implemented by a **Sonnet** session working from GitHub. It only sees what is
  pushed. **Push `main` after every phase**, or the next session works on stale files (this already
  happened once: Phase A was built without `docs/rules/`).
- One phase per session, then stop for the user's OK. Phase work goes on a branch, then is merged
  into `main` and pushed.
- Review each phase report against the code. The Phase B report missed one flaky test (now fixed).

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
- **Tier 2 is slower on this variant** (30–50 hands/s here vs 58–190 in Hold'em). It is still inside
  the bank (~9 s of 60 s per 400 hands locally); Phases D/E budget it properly.
- Tier 2 is **not deterministic run to run** (its sample counts depend on wall-clock time), so equal
  seeds don't give equal chips. Compare with enough pairs and SEs.

## Open items for the next phases

- **Phase C:** the full-match smoke test must run over the real `pokerbots` protocol. Phase B's ran
  over the placeholder protocol.
- **Phase D:** three file-reading loaders to remove (`bot/brains/params.py`, `bot/sim/tables.py`,
  `bot/game/rules_spec.py`). The hard deadline can currently reach 15 s, and replies must be under 5 s.
- **Phase E:** ask the user about CFR (plan, Phase E step 5). Don't start it.
- **Phase F:** the user is generating LLM bots for Discard Hold'em (same prompt per model, both PDFs
  attached), saved under `Opps/discard/<model>/bot.py`. The user picks the held-out ones.
- **1 Nov:** the Problem Statement comes out → Phase H checks (showdown rule, provisional limits).

## Environment

- Repo: `/home/fioriv/synergy/PokerBot`, GitHub `ariv-IIITB/PokerBot`, branch `main`.
- Python 3.11 via uv: `.venv/bin/python -m pytest -n auto` (system python is 3.12; don't use it for tests).
- `Opps/opp1..opp4`: the Hold'em LLM bots (lab only, never copy into `bot/`). `opp4` used to be a
  symlink to `opp 4`; it is a real folder now.
