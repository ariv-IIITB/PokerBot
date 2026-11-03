# Tier 4: parallel sub-plans

The design and its reasons are in `docs/TIER4_PLAN.md` (v5). This folder splits it into **small sub-plans,
one Claude session each**, so no session has to carry the whole plan. A session reads `CLAUDE.md`, this
README, **its own sub-plan** and the handoff notes it lists. Nothing else unless its sub-plan says so.

## Streams

```
            Tue 3        Wed 4        Thu 5        Fri 6        Sat 7        Sun 8        Mon 9      Tue 10
S  shared   S0 ──► recordings + score script (others need them only at their gates)
P  portfolio PA ──► PB tuning (night) ─┐
                    PC selection ──────┴► PD gate P ─────►
D  discard  DA rollouts + retune ─────────────────────┐
            (after S0) DB learn their rule ──────────┴► DC our discard ──►
R  river    RA spike ───► RB integrate ─────────────► RC gate R ─────►
I  merge                                                                          I1 ────────►
```

Sub-plan IDs use letters so they don't clash with the section labels (P0–P4, D0–D4, R0–R1) in `TIER4_PLAN.md`.

| id | sub-plan | plan sections | branch | needs before starting | needs before its gate | model, where |
|---|---|---|---|---|---|---|
| **S0** | `S0_recordings.md`: recorder change, 12 fresh pairs per bot, match-score script | P0b | `tier4/s0` | — | — | Sonnet, laptop |
| **PA** | `PA_members.md`: gate X, `tier4p` with forced members | P0a, P1 (code) | `tier4/p` | — | — | Opus, laptop |
| **PB** | `PB_tuning.md`: member grids + confirmations | P1 (tuning) | `tier4/p-tune` | PA | — | Sonnet, cloud |
| **PC** | `PC_selection.md`: selection, bail-out, stop-loss, adversary bot | P2 | `tier4/p-sel` | PA | — | Opus, cloud |
| **PD** | `PD_gate.md`: merge PB + PC, gate P, timing, package | gate P | `tier4/p` | PB + PC | S0 | Sonnet, laptop |
| **DA** | `DA_rollouts.md`: smart rollouts on Tier 3 + retune | D1 | `tier4/d` | — | — | Sonnet, cloud |
| **DB** | `DB_learn.md`: rule fit, "do they read our discard", learned keep rule if go | D0, D4, D2 | `tier4/d-learn` | S0 | — | Opus, cloud |
| **DC** | `DC_our_discard.md`: merge DB, our discard vs their rule, discard budget | D3 | `tier4/d` | DA + DB | — | Sonnet, laptop |
| **RA** | `RA_spike.md`: solver + ranges, speed and exploitability | R0 | `tier4/r` | — | — | Opus, cloud |
| **RB** | `RB_integrate.md`: solver in Tier 3's river behind a flag, own range, timing | R1 | `tier4/r` | RA (go) | — | Opus, laptop |
| **RC** | `RC_gate.md`: accounting SE, gate R, restricted p | gate R, restricted p | `tier4/r` | RB | S0 | Sonnet, laptop |
| **I1** | `I1_integrate.md`: merge P + D + R, combined gates, held-out, package | Mon 9–Tue 10 | `tier4/main` | PD, DC, RC | — | Opus, laptop |

**Day 1 (Tue 3) runs four sessions at once: S0 and PA on the laptop, DA and RA in the cloud.** After that, a session starts as soon as its
"needs before starting" are pushed. "Needs before its gate" only blocks the final measurement, not the code.
PB and PC run at the same time (different files).

**One change from `TIER4_PLAN.md`:** the river solver goes into **Tier 3's river behind a flag**
(`t3_river_solver`), not into `tier4p`. That keeps R independent of P, and `tier4p`'s members inherit it at I1.
Gate R therefore compares Tier 3 with vs without the solver.

## Rules every session follows

1. **Branch from `origin/tier4/base`** (= `main` with Phase H + the exploit layer X1–X3; fast suite 1290 passed,
   2 skipped). Push your branch at the end. Don't merge into `main` or into another stream's branch (I1 does that).
2. **Edit only the files your stream owns** (table below). `bot/embedded.py` is generated: after changing params
   or data, run `.venv/bin/python -m tools.embed_data` and commit it. Never hand-merge it.
3. **Where it runs, and CPU:**
   - **Cloud** (own machine per session): RA, PC, DB, PB, DA. Start with `nproc` and set `--processes` to that
     minus 1. **Cloud numbers are provisional (cloud).** Every binding measurement (go/no-go, KEEP confirmation,
     timing) runs on the laptop; the next laptop sub-plan in the stream re-runs it as its step 0. Setup: `uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt`.
   - **Laptop** (14 cores, shared): S0, PA, PD, RB, RC, DC, I1, and **every timing check** (`tests/test_timing_slow.py`,
     `tests/test_river_timing.py`, `lab.timing_bench`, the package check). The "server is ~2× slower" rule is calibrated
     on this laptop; a cloud machine's timing numbers don't count. A cloud session that changed `bot/` writes
     "timing not checked (cloud)" in its handoff, and the next laptop session runs the timing check first.
     On the laptop, `--processes` = floor(12 / laptop sessions running when you start, counting yourself), at least 2,
     fixed for the whole session (both arms of a comparison must match). I1 runs alone and uses 12. A session that
     joins later may push the total above 12 for a while; that's fine, because binding comparisons are always within
     one session, back to back.
   - **The laptop lock** (no code, one wrapper): every `lab.eval` / `lab.opps.record` on the laptop runs under
     `flock -s /tmp/pokerbot_laptop.lock <command>` (shared: evals run side by side); every timing check
     (`tests/test_timing_slow.py`, `tests/test_river_timing.py`, `lab.timing_bench`, the package check) runs under
     `flock -x /tmp/pokerbot_laptop.lock <command>` (exclusive: it waits for running evals, and new evals wait behind it).
     Cloud sessions skip the lock.
   - Budgets are wall-clock, so the two arms of a comparison run **back to back on the same machine**, and numbers
     from different machines are never compared with each other. Every KEEP is confirmed once on fresh seeds.
   - Each handoff says which machine its numbers came from (`nproc`, cloud or laptop).
4. **Seeds:** use only your block (below), so no two sessions reuse seeds.
5. **Two-part KEEP** (every pool gate): `lab.eval --compare` on chips from a **locks-off** run (sum up, no bot down
   > 2 SE) **and** the mean match score from a **locks-on** run not lower by > 2 SE (S0's `lab/opps/score_compare.py`;
   until S0 lands, compare the score lines by hand). The training pool is `--pool train`.
6. **Held-out bots** (conv_opp4, eqrandom, geometric): no session but I1 runs them, and only with `--final`.
7. **Tests:** fast suite green on 3.11 before every push (`.venv/bin/python -m pytest -n auto`); `tests/test_timing_slow.py`
   (`-m slow`) after any `bot/` change.
8. **Handoff:** end by writing `docs/tier4/handoff/<id>.md` (≤ 40 lines): what's done, numbers with ± SE and pairs,
   the commit, decisions (go/no-go, KEEP/DROP), and what the next sub-plan needs. Commit and push it on your branch.
   The next session reads that note, not your transcript.
9. If three fixes in a row fail, or a go/no-go says no, stop and write the handoff.

## User checkpoints

The user reviews only the go/no-go handoffs: **PA** (gate X), **RA** (GO/NO-GO, provisional), **DB** part 1 (is there
a rule to learn), **PD** (gate P), **RC** (gate R) and **I1** (what ships). Every other session starts as soon as its
prerequisite has pushed its handoff.

## File ownership

| owner | files |
|---|---|
| S0 | `lab/opps/record.py`, `lab/opps/score_compare.py` (new), `logs/records/` |
| P | `bot/brains/tier4p.py` (new), `bot/brains/tier4p_select.py` (new, PC), `bot/brains/exploit.py`, `bot/main.py` (the registry line only), `lab/eval.py` (`LOCK_BRAINS` only), `lab/sparring/adversary.py` (new), `tests/test_tier4p*.py`, `tests/test_timing_slow.py`, `docs/reports/TIER4P.md` |
| D | `bot/sim/rollout.py`, `bot/sim/inference.py`, `bot/sim/discard.py`, `bot/config/tier3.json` (new: D's tuned Tier 3 values), `lab/opps/discard_rules.py` (new), `tests/test_discard_*.py`, `docs/reports/TIER4_DISCARD.md` |
| R | `bot/strategy/river_solver.py` (new), `bot/strategy/own_range.py` (new), `bot/brains/tier3.py`, `bot/timing.py`, `lab/opps/accounting.py`, `lab/river_bench.py` (new), `tests/test_river_*.py`, `docs/reports/TIER4_RIVER.md` |
| I | merges only; `docs/STATUS.md`, `docs/SUBMISSIONS.md` |

Not ours: `bot/cfr/`, `lab/cfr/fast/` and `docs/reports/TIER4.md` (the teammate's CFR, Tier 5).
A sub-plan that finds it must touch another stream's file stops and says so in its handoff.

## Seed blocks

| block | owner |
|---|---|
| 0–11 | X0 fixtures (read only) |
| 8000–8099 | PA gate X |
| 9000–9011 | S0 recordings (read only for everyone else) |
| 10000–10999 | PB tuning; 11000–11999 PB confirmations |
| 12000–12999 | PD gate P |
| 20000–20999 | DA; 21000–21999 DB and DC |
| 30000–30999 | RC gate R |
| 40000–40999 | I1 (incl. held-out `--final`) |

## Slip rule

This README is the source of truth for the slip order (it replaces the one in `TIER4_PLAN.md`). I1's retry rule is in
`I1_integrate.md`.

If a day slips, drop in this order: RC's restricted p → DC → DB's learned rule (keep its measurements) → R entirely.
P and DA are not optional. If gate P fails, PD's handoff says so, and I1 ships the incumbent (`tier3x` if gate X
passed, else `tier3`) plus any D and R KEEPs.
