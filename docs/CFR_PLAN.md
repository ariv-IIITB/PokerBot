# CFR hybrid bot (Tier 4): the plan

> **Superseded on 2026-10-31 by `docs/CFR_BUILDMAP.md`** (none of this was built; dates passed; Tier 3
> now ships and the exploit layer comes first). Kept for its reasoning.

Written 2026-10-29. Read `CLAUDE.md`, `docs/STATUS.md` and `docs/PART4_PLAN.md` first.
This plan replaces the "CFR is a no-go" verdict of `docs/PART3_ROADMAP.md` for Discard Hold'em:
that verdict came from 2 h of training on 1 core with 8 coarse buckets.

## 0. Goal and assumptions

**Goal.** A bot whose betting comes from a CFR blueprint (hard to exploit), whose river is solved
live on the actual cards and bet sizes, and whose exploitation comes from the Tier 3 "Ivey" adaptation
layer. It ships only if it beats Tier 3 and Tier 2 in the lab (section 8).

**Assumed done before K4–K5** (K1–K3 do not depend on them and start now, in parallel):
- Tier 2 updated for Discard Hold'em (PIMC discard, tables, inference) — Phase E.
- Tier 3 "Ivey" built — Phase G: `oppstats` (per-spot Beta counts, bluff index), board texture,
  the capped adaptation rules (≥ 20 samples, ±15 points).
- The opponent pool — Phase F: `Opps/discard/*` LLM bots, train / held-out split.

**Test opponents.** Strong: Tier 3, Tier 2 (updated), opp3. Light: opp1, opp2, opp4. Plus the
Phase F train pool; the held-out pool is used once, at the end.

**Kill rule.** If the blueprint alone fails gate A (section 8), stop: Tier 3 ships. Every step
after that is kept only if it measurably helps.

## 1. The bot at runtime

Per decision, in this order (each layer falls back to the one below it on error, missing data
or a tight time budget):

```
endgame lock (Tier 2)            lead safe -> check/fold, as today
discard request                  Tier 2 PIMC discard (+ optional "hide" choice, Tier 3 G7)
preflop / flop / turn bet        blueprint lookup -> probabilities over abstract actions
river bet                        live river solver (section 4) -> probabilities
                                 (falls back to the blueprint if over budget)
all streets                      adaptation layer shifts probabilities (section 5)
                                 sample one action (seeded rng), map to a concrete amount
                                 legality check + clamp (bot/actions), as today
anything off-tree / any error    Tier 2 decision
```

The opponent's real bet sizes are mapped onto the tree with the pseudo-harmonic rule already in
`bot/abstraction.py`. On the river the solver uses the real size, so no mapping is needed there.

## 2. K1 — the abstraction

The abstraction decides the ceiling. Keep it in one place, `bot/abstraction.py` (moved out of
`lab/` on 2026-10-29 so the runtime can import it), and use the same code for training and at
runtime (as `tests/test_cfr_runtime.py` does today).

**Infoset key** = (street, card bucket, board texture class, betting history this hand).

**Cards.**
- Preflop: the **1,755** lossless 3-card classes (suits folded together; counted 2026-10-29).
- Flop (3 hole cards, before the discard): k-means EMD buckets (`lab/buckets.py` has `kmeans_emd`)
  over histograms of best-2-after-discard equity, plus draw/blocker features. Start with 200.
- Turn and river (2 hole cards after the discard; both discards are public dead cards): EMD
  buckets on the turn (200), equity buckets plus a blocker flag on the river (100).
- Board texture class (public): paired / monotone / two-tone / rainbow × connected or not.
  It lets the blueprint learn "small bets on dry boards".
- shortcut: the opponent's discarded card only enters as a dead card, not as its own key part;
  upgrade if the discard ablation (section 8) shows it matters.

**Actions** (the tree respects the 4-bet cap; preflop the BB is the first bet):
- Preflop: fold, call, open to 2.5 bb, 3-bet to ~3×, 4-bet to ~2.2×, all-in.
- Postflop bets: check, 33 %, 75 %, 125 % (river only), all-in.
- Raises: ~2.5× the bet, all-in. Fold / call always.

**Size budget.** Count infosets before training (a script that walks the abstract tree).
Target ≤ ~1.5 M infosets. If over, drop the 125 % size first, then cut river buckets.

**Discard in training.** A fixed, fast policy: keep the best 2 cards by equity (Tier 2's fast
discard). Both discards become public dead cards. CFR learns betting only; the real discard stays
with Tier 2 at runtime.

**Done when:** infoset count and estimated table size are in the report, and a test checks the
runtime key equals the training key on 1,000 random hands.

## 3. K2 — the trainers

Two trainers, same abstraction, same export format. Pick the one with lower exploitability per
hour of wall clock on the same small game.

**K2a — external-sampling MCCFR on CPU (the reference).**
- Start from `lab/cfr/mccfr.py` (already external sampling). Changes:
  - Linear CFR / DCFR discounting (α = 1.5, β = 0, γ = 2) instead of CFR+ flooring;
  - skip actions with very negative regret after a warm-up (the Pluribus recipe);
  - flat NumPy tables indexed by infoset id instead of dicts (needs K1's fixed indexing);
  - workers in separate processes sharing one table (`multiprocessing.shared_memory`), ~10
    workers on the laptop.
- External sampling walks the tree one sample at a time, so **it does not use a GPU**.

**K2b — vectorized CFR on GPU (PyTorch, lab only).**
- Public chance sampling: sample one board (and both discards), then update **all** hand buckets
  of both players at once as tensor operations. Exact showdown values by sorting hand ranks.
- DCFR, alternating updates, average strategy exported.
- Runs on CPU too (same code), so it is developed and tested on the laptop before any GPU hour.

**Both:** checkpoint every 15 min and resume from a checkpoint; fixed seeds; a progress log
(iterations/s, infosets touched, % visited < 10 times).

**Validation (before any long run):** Kuhn reaches −1/18; Leduc exact exploitability falls
steadily (`lab/cfr/exact.py`); K2a and K2b agree on Leduc and on a small Discard Hold'em tree
(short stacks, 2 sizes).

**Compute plan.**
1. Laptop (14 cores): K2a runs from day 1 for gate A.
2. Camber (5 free GPU hours/month, Student Pack): K2b smoke test — CUDA works, real speed,
   what size fits.
3. The rented GPU (6 h): one long K2b run of the final abstraction, only after gate A passes.
   Run the exact script locally on a tiny config first, including the export.
4. Azure student credit ($100, if the vCPU quota allows): a second abstraction on K2a in parallel,
   so gate A compares two versions.

**Export.** Average strategy → uint8 probabilities per infoset, drop infosets visited < N times
(they fall back to Tier 2), zlib + base64 into `bot/embedded.py` via `tools/embed_data.py`, as a
`"blueprint"` entry of `ARTIFACTS` (`bot/artifacts.py` checks it was built for the spec).
The embed cap is 3 MB today and the zip limit is 5 MB: measure the existing tables first and
raise the cap only as far as the zip check allows.

## 4. K3 — the live river solver (in `bot/`, NumPy, one core)

- **Inputs:** our range and the opponent's range over 2-card combos (minus board, both discards and
  our cards), pot, stacks, bets so far, raises left.
  - Our range: the blueprint's probability of our own line (we know our strategy).
  - Opponent range: `Opponent.range_weights(rec, combos)` (`bot/opponent.py`), blended with "they played the blueprint" (a CONFIG
    weight, tuned in the lab).
- **Tree:** the real current bet plus 33 / 75 / 125 % / all-in, raises up to the cap.
- **Algorithm:** full-width vectorized CFR (DCFR) over ~1,000 combos per side; showdown values by
  sorting hand ranks and prefix sums (O(n) per node).
- **Time:** iterate until a per-decision budget (from the bank, like Tier 2's budget), minimum
  ~50 iterations; else use the blueprint. Target p95 < 60 ms on the laptop (server ≈ 2× slower).
  Measure; do not guess.
- **Safety:** start with plain re-solving from the blueprint ranges. If tests show it can be
  exploited (e.g. by a bot that overbets the river), add Libratus-style safe re-solving.
- **Tests:** on small toy rivers the solver matches `lab/cfr/exact.py`; prefix-sum showdown equals
  brute force; never exceeds its budget in the timing tests.

## 5. K4 — the adaptation layer (from Tier 3)

- Reuse Tier 3's `oppstats` and adaptation rules as one function:
  `adjust(probs, spot, stats) -> probs`. If Tier 3 has the logic inside its brain, move it to a
  shared module first (no copy-paste).
- Same caps as Tier 3: a spot moves only after ≥ 20 samples, at most ±15 points per action.
- Rules: value-only bettor → fold bluff-catchers to big bets, bluff less; over-bluffer → call wider;
  high fold-to-c-bet → bet more, small; calling station → no bluffs, value three streets.
- On the river, a cleaner option: feed the opponent model into the solver's **opponent range**
  (e.g. value-heavy betting range) instead of shifting the output. A/B both.

## 6. K5 — the brain

- `bot/brains/tier4.py`: `Tier4Brain`, a policy over `bot/situation.py` (reconstruction, PIMC
  discard, equity fallback, endgame lock) and `bot/opponent.py`, plus Tier 2/3 parts (oppstats, lock,
  timing). All numbers in one `DEFAULTS` dict so `lab.eval tier4:...` can change them.
- Register `tier4` in `bot/main.py:BRAINS`; the default brain stays as is until section 8 passes.
- Strategy table decoded once at start-up (inside the 5 s; measure), held in memory (≤ 1 GB total;
  `lab.memory_check`).
- `tools.package_submission --brain tier4 --zip` must pass its checks (size, no file reads, sandbox).
- `lab/cfr/brain.py` stays lab-only; tier4 reuses its lookup ideas with code in `bot/`.

## 7. K6 — self-play and improvement (detail later)

- Snapshot every kept version (`lab/versions.py`) and play the current bot against older ones and
  against Tier 2/3, so a change that breaks something old shows up.
- Hunt holes: train a best response to the frozen blueprint inside the abstraction, see where it
  wins, fix the abstraction there.
- The details are decided after gate B.

## 8. Gates (all with `lab.eval`, duplicate pairs, standard errors, accounting report)

| Gate | What | Pass |
|---|---|---|
| A | blueprint alone (+ Tier 2 discard/fallback) | vs Tier 2 **and** opp3: match score > 0.5 by > 2 SE, 100 pairs each, locks on. Else stop. |
| B | + river solver | beats gate-A bot head to head (100 pairs, > 2 SE); river showdown line in accounting improves |
| C | + adaptation layer | better on the light pool; no strong opponent worse by > 2 SE |
| D | discard check | Tier 2 PIMC discard vs fallback discard, 50 pairs: decides whether the discard key upgrade (K1) is worth it |
| Ship | tier4 as default | beats Tier 3 head to head (100 pairs, locks on, > 2 SE); better on the train pool; held-out pool (`--final`, once) not worse; timing and memory pass at 400 and 1,000 hands assuming a 2× slower server |

Each gate's numbers go in `docs/reports/TIER4.md`. A step that doesn't pass is switched off in
`DEFAULTS`, not debugged forever (three failed fixes in a row → stop and report).

## 9. Timeline (deadline 15 Nov, 23:59 IST)

| Dates | Work | Depends on |
|---|---|---|
| now – 31 Oct | K1 abstraction + infoset count; K2a changes; Leduc A/B (CFR+ vs DCFR, pruning) | — |
| 31 Oct – 3 Nov | K2a training on the laptop; K2b written and checked on Leduc; Camber smoke test | K1 |
| ~3–4 Nov | **Gate A** | K2a |
| 4–6 Nov | rented-GPU run (K2b, final abstraction); K3 river solver | gate A |
| 6–9 Nov | K3 tests and timing; gate B; K4 once Tier 3 exists | K3, Tier 3 |
| 9–11 Nov | K5 brain + package; gate C, gate D | K4 |
| 11–13 Nov | ship gate; held-out run | everything |
| 14–15 Nov | freeze: the best passing bot ships (Tier 4, else Tier 3, else Tier 2) | — |

K1–K3 are lab work and do not touch Tier 3's files, so they can run in their own session while
Tier 3 is built.

## 10. Risks

- **Abstraction too coarse** (what lost before) → finer buckets with GPU compute; the river solver
  covers the street where it matters most.
- **Table too big for 5 MB** → prune rarely visited infosets (fall back to Tier 2), drop the 125 %
  size, fewer river buckets (the solver plays the river anyway).
- **Off-tree bet sizes** from LLM bots → pseudo-harmonic mapping; the river solver uses real sizes.
- **River solver too slow on the server** → time-boxed, falls back to the blueprint.
- **Bad opponent ranges** feeding the solver → blend weight tuned in the lab; inference trust
  already fades against bots it doesn't fit.
- **GPU hours wasted** → nothing runs on a paid GPU that hasn't run end to end locally.
- **Time** → gate A on 3–4 Nov; if it fails, all remaining time goes to Tier 3.

## 11. Files

Changed (bot): `bot/abstraction.py` (Discard Hold'em buckets, sizes, texture).
New (lab): `lab/cfr/count_infosets.py`, `lab/cfr/vec_cfr.py` (K2b,
PyTorch), changes to `lab/cfr/mccfr.py` and `lab/cfr/train.py`.
New (bot): `bot/cfr/blueprint.py` (lookup), `bot/cfr/river_solver.py`, `bot/brains/tier4.py`,
shared adaptation module (moved from Tier 3).
Changed: `tools/embed_data.py` (strategy table), `bot/main.py` (registry), `docs/STATUS.md`.
Tests: key equality, export round trip, solver vs exact on toy rivers, prefix-sum showdown, timing.
