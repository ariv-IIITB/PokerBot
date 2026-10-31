# Build map: Tier 4, a CFR equilibrium bot with an exploit layer

Written 2026-10-31 at `main` = `32b392e`. **This supersedes `docs/CFR_PLAN.md`** (29 Oct). That plan's
ideas (K1–K6, gates A–D) still hold, but none of it was built, its dates have passed, and three
facts have changed since: Tier 3 ships (not Tier 2), the opponent pool exists and is profiled
(`docs/book/pokerbot_book.html` §2.8–2.9), and the exploit layer is now the top priority.

Read first: `CLAUDE.md`, `docs/STATUS.md`, `docs/reports/PHASE23.md` (why the last CFR lost),
`docs/reports/TIER3.md`, the book's Chapter 1 §1.6–1.9 (theory) and Chapter 2 §2.8–2.12 (data).

Deadline **15 Nov 2026, 23:59 IST**. Freeze **13 Nov evening**; the user uploads on 14 Nov.
Today is **31 Oct**; the Problem Statement arrives **1 Nov** and may change rules.

---

## 0. The one-paragraph version

Build two things in parallel and merge them only if the numbers say so.
**Track X (exploit layer)** goes on Tier 3 first and ships no matter what happens to CFR: it is
where the measured chips are (over-folders and value-only river bettors, book §2.8).
**Track C (CFR)** builds a *fast* trainer (Numba, multi-core; the old one did 68 iterations/s),
an abstraction whose table is about 1 MB, a blueprint brain `tier4` that plays the blueprint
and falls back to Tier 3, then the exploit layer on top. CFR has hard **kill gates**: if the
blueprint can't beat Tier 3 head-to-head by **6 Nov** (gate A), CFR stops and all time goes
to Track X. Whatever passes the ship gate on 12–13 Nov is the bot. Tier 3 stays as the fallback
inside every decision and as the whole bot if nothing else passes.

```
            31 Oct  1  2  3  4  5  6  7  8  9 10 11 12 13 | 14 15
Track X     X0 X1 ── X2 ─── X3 ──── X4 (loop tuning) ───── |
Track C     C0 C1 ─ C2 ─ C3 ─ C4 ─ C5 │A│ C6 ─ C7 │B│ C8  | upload
Merge                                      M1 ─── M2 │SHIP│
Phase H     (1 Nov: read the Problem Statement, re-check every rule in §2)
```

---

## 1. What exists, what failed, what we know

| Thing | Where | State |
|---|---|---|
| External-sampling MCCFR + CFR+ | `lab/cfr/mccfr.py` | correct (Leduc → 0.020), **68 it/s**, pure Python |
| Abstract game over the real engine | `lab/cfr/abstract_game.py` | correct but slow (it runs `bot/game` per node) |
| Shared abstraction | `bot/abstraction.py` | 8 noisy equity buckets (64 samples), sizes ½ pot, pot, all-in |
| Trainer CLI, export, uint8 tables | `lab/cfr/train.py`, `mccfr.export_uint8` | works |
| Lab CFR brain | `lab/cfr/brain.py` | plays a table, falls back to Tier 2; lab only |
| Exact evaluation / best response | `lab/cfr/exact.py` | Kuhn, Leduc |
| Runtime/trainer key check | `tests/test_cfr_runtime.py`, `lab/cfr/runtime_audit.py` | works |
| Lossless 3-card classes (1,755) | `bot/sim/canonical.py`, `data/discard_holdem/classes.npy` | committed, embedded |
| Embedded artifacts | `bot/artifacts.py`, `tools/embed_data.py` | `tables` today; add `blueprint` |

**Why it lost before** (`docs/reports/PHASE23.md`): (1) undertraining: 0.9 M infosets, 75%
seen fewer than 10 times after 2 h; (2) abstraction quality: 64-sample buckets put ~38% of hands
one bucket off; (3) an exploration bias, since fixed. Even a small, well-trained 30-bb tree lost
to Tier 2 (−0.09 chips/hand). **Lesson: speed and bucket quality first, or don't bother.**

**Sizes, measured 31 Oct** (`scratchpad/count_tree.py`, stacks 200, cap 4 bets, BB = first bet):

| Action menu | decision-node histories (pre / flop / turn / river) | infosets with buckets (1755 / 200 / 200 / 100) | table, uint8 × ~3 actions |
|---|---|---|---|
| rich (½-pot + ¾ + 1¼ river) | 7 / 88 / 660 / 4,150 | 577 k | ≈ 1.7 MB raw |
| lean (½, pot, all-in) | 7 / 98 / 774 / 3,754 | 562 k | ≈ 1.7 MB raw |
| lean, buckets 1755 / 100 / 50 / 50 | — | 248 k | ≈ 0.7 MB raw |

The zip today is ~190 KB. **Size is not the constraint; visits per infoset are.** At 500 k
infosets, 100 visits each = 50 M infoset-visits. The training speed (§4) decides the abstraction,
not the other way round.

**What the opponents do** (measured, book §2.8): four of nine pool bots fold 56–79% to our
river bets; six of nine almost never bluff the river. An equilibrium bot by itself will not
collect this. That is why the exploit layer (Track X) comes first and also sits on top of Tier 4.

---

## 2. Decisions to take on day 0 (my recommendation first)

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Trainer technology | **Numba-JIT external-sampling MCCFR on CPU**, multi-core; GPU only for an optional vector trainer later | external sampling walks a tree one sample at a time: a GPU is bad at that. Numba gives 100–1000× over pure Python with Python syntax; lab code may use any library. |
| D2 | Game core for training | **A hand-written fast game in Numba** (`lab/cfr/fast/`), proven equal to `bot/game` by tests | running the real engine per node is what made 68 it/s |
| D3 | Discard in training | **Fixed policy: keep the two cards with the best equity vs random on this flop**; both discards become public dead cards | CFR learns betting; the runtime discard stays Tier 2's PIMC discard (better). Modelling the discard as a CFR action is a later upgrade (§9) |
| D4 | Action menu | **lean** (preflop: fold, call, raise 2.5×, 3× re-raise, all-in; postflop: check/call, ½ pot, pot, all-in; raise: 2.5×, all-in) | same size as rich; fewer translation errors with ½/pot |
| D5 | Buckets | preflop **1,755 lossless**; flop **100** (2-D grid over post-discard E[HS], E[HS²]); turn **100**; river **50** (exact HS vs random + a blocker bit) | deterministic, cheap to compute at runtime, no k-means file to ship |
| D6 | Where the blueprint plays | staged: **preflop+flop first**, then turn, then river | each street is its own gate; an early street that wins can ship alone |
| D7 | Fallback | **Tier 3** (not Tier 2) for anything off-table, any error, any tight budget | Tier 3 is the shipped champion |
| D8 | River solver | **Idea only until gate B**; build only if the blueprint river loses at river showdowns | stays within the "CFR as idea" boundary unless the data ask for it |
| D9 | Compute | laptop (all cores) for development and overnight runs; your GPU only for the optional vector trainer | measured throughput decides; no paid GPU hour before an end-to-end local run |

Phase H interaction (1 Nov): if the showdown rule, blinds, stacks, raise cap or discard rule
change, update `variant/catalog/discard_holdem.json` first, then §1's size table (rerun the
counter), then every C-step's tests. **The fast game core must take its numbers from the spec**
(stack, blinds, cap) so a rule change is a config change, not a rewrite.

---

## 3. Track X: the exploit layer on Tier 3 (ships no matter what)

Design: book §2.10. Branch `x/exploit-layer`. Owner: one session per step; every step test-first
(`/tdd`), full suite after each change, acceptance by the unchanged `lab/eval.py --compare`.

### X0. Recorded evidence and fixtures (31 Oct – 1 Nov, ½ day)
- Move the profiling recorder (`scratchpad/book/profile_run.py`, `analyse.py`, `traits.py`)
  into `lab/opps/` as `lab/opps/record.py` and `lab/opps/traits.py` (lab only).
- Save 4 recorded matches per training bot as test fixtures (`tests/fixtures/opp_records/*.json.gz`,
  < 1 MB total).
- **Done when** `lab.opps.traits` reproduces the book's table 2.4 numbers on the fixtures (test).

### X1. Trait detectors in `bot/` (1–2 Nov, 1 day)
- New `bot/strategy/traits.py` (stdlib + NumPy only):
  `class TraitTests: observe(event) ; state() -> {"overfolder": (llr, verdict), "station": …, "river_bluffer": …}`
  - SPRTs from book §1.4.2 with α = β = 0.05: over-folder (fold to our postflop bet 0.6 vs 0.4),
    station (continue vs river bet 0.8 vs 0.5), preflop folder (fold to our open 0.55 vs 0.35).
  - Shrunk rates for size (Beta prior, K = 15, as `oppstats`).
  - CUSUM on each decided trait (book §1.9.3): alarm resets the verdict to "undecided".
- Feed it from `bot/opponent.py`'s existing message stream (do not add a second parser).
- **Tests**: on X0 fixtures, verdicts match table 2.4 (yes for exploiter / rules / conv_opp3 within
  120 hands; no for stations and aggressors); a synthetic bot that switches from folding to calling at
  hand 100 trips the CUSUM within 40 more decisions.

### X2. Type posterior (2–3 Nov, 1 day)
- `bot/strategy/types.py`: a library of 6 styles (over-folder, value-only, station, trapper,
  aggressor, balanced/unknown) with per-spot action probabilities taken from the profiling data,
  embedded as a small artifact (`ARTIFACTS["types"]`, < 20 KB) via `tools/embed_data.py`.
- Naive Bayes over (street, spot, action-bucket) symbols, Laplace-smoothed, plus an explicit
  "unknown" class with population-average probabilities.
- Output: posterior over types + the *implied slow traits* (river bluff share per type).
- **Tests**: held-out-seed accuracy ≥ the book's numbers; an unseen style (`random_legal`) ends
  mostly "unknown", not confidently wrong.

### X3. Counter-moves with λ (3–6 Nov, 2–3 days)
- `bot/brains/exploit.py`: `ExploitLayer.adjust(params, spot, traits, types) -> params`, a pure
  function used by Tier 3 now (wrapping `Tier2Brain.adjusted`) and by Tier 4 later.
- λ per counter-move (book §1.9.4): 0 until the relevant SPRT decides, then ramps to 1 over 20
  more observations; drops to 0 on a CUSUM alarm.
- Moves, in order of measured value (book §2.10.2):
  1. **over-folder** → raise bluff frequency on flop/turn/river up to `bluff_max` (start 0.6) and
     prefer the size whose break-even fold rate is ≤ ½ their shrunk fold rate;
  2. **value-only river bettor** (type posterior ≥ 0.7) → river call margin + `vo_margin` (start 0.12);
  3. **station** → `bluff_freq` 0, value thresholds −0.05, value size +30%;
  4. **preflop folder** → button open range +20 points;
  5. **trapper** → fold medium hands to its river raise.
- The old caps (±15 points, gate 20) stay as the λ = 0 baseline; the layer widens them with λ.
- **Tests at the policy seam**: a confident over-folder posterior makes a checked-to weak hand bet;
  a value-only posterior folds a bluff-catcher to a pot river bet; λ = 0 reproduces Tier 3 exactly
  (same actions on fixed seeds).
- **Gate X**: `lab.eval tier3x --pool train --pairs 50` vs `tier3` with `--compare`: KEEP, then
  fresh seeds 50 pairs again; held-out bots not tuned on; also vs `tier2`, `starter`, sparring:
  no drop > 2 SE. Timing ≤ 50% at 2×, memory < 500 MB.

### X4. League tuning of the layer's numbers (6–12 Nov, background)
- The loop of book §2.11 over X3's ~10 numbers (`bluff_max`, `vo_margin`, ramp lengths, SPRT
  thresholds). Overnight runs; gate = X3's gate on fresh seeds.
- **Ship**: if gate X passes, `tier3x` becomes the default brain by 9 Nov (upload candidate #5).

---

## 4. Track C: the CFR blueprint

Branch `cfr/tier4`. All trainer code is `lab/` (anything allowed); only `bot/abstraction.py`,
`bot/cfr/*` and `bot/brains/tier4.py` ship (stdlib + NumPy).

### C0. Specification freeze (31 Oct – 1 Nov, ½ day)
- Write `docs/cfr/ABSTRACTION_V1.md`: D3–D5 exactly (sizes as formulas, bucket formulas, history
  string format, rounding rules). This document is the contract between trainer and runtime.
- After the Problem Statement (1 Nov): confirm or update stacks, blinds, raise cap, showdown rule.
- **Done when** the document has a worked example (one full hand → every infoset key).

### C1. Fast game core (1–3 Nov, 2 days)
- `lab/cfr/fast/game.py` (Numba `@njit`):
  - deck as `uint8`, deals from a seeded PCG64 stream per iteration;
  - betting state machine on integer chips (`contrib[2]`, `to_act`, `raises_left`, `street`);
    abstract actions from the lean menu with the **same rounding as `bot.actions.pot_fraction_raise`**;
  - fixed discard policy (D3);
  - payoffs from a 7-card evaluator: `lab/cfr/fast/eval7.py`, 5-card lookup tables generated from
    `bot/evaluator.py` (so the hand order is the engine's), 21 combos per 7 cards.
- **Tests (the most important ones in the track)**:
  - 20,000 random abstract action sequences: chips, legality, terminal payoffs equal `bot/game`'s
    (`lab/cfr/abstract_game.py` as the oracle);
  - evaluator equals `bot/evaluator.py` on 1 M random 7-card hands;
  - discard policy equals `bot/sim/discard.py`'s fast mode on 10,000 flops.

### C2. Bucketing (2–4 Nov, 2 days, parallel with C1)
- `bot/abstraction.py` v2 (shipped code, NumPy only) **and** a Numba twin in `lab/cfr/fast/buckets.py`,
  both computing the same integers:
  - preflop: class id (1,755) from `ClassIndex` (exists);
  - flop (3 hole cards, before the discard): keep-best-2 equity vs random E[HS] and E[HS²] by **fixed-seed**
    sampling (seed = hash of cards, as today), but with **2,000 samples** (not 64) → 10 × 10 grid;
  - turn: same with 1,000 samples → 100 cells;
  - river: **exact** HS vs all opponent 2-card hands (≈ 900 evaluations) → 40 quantiles + 1 blocker
    bit (do we hold a card of the board's flush suit / straight card) → 80 buckets → cap 50 by merging.
- **Runtime cost budget**: bucket computation ≤ 15 ms per decision on the laptop (server ≈ 2×);
  measure with `lab.bench_equity`-style micro-bench. If over: precompute flop E[HS] per
  (canonical flop, 3-card class) offline into an embedded table (size check first).
- **Tests**: Numba twin == NumPy runtime on 5,000 random situations (exact equality of bucket ids);
  bucket-boundary stability (the same cards in a different order give the same bucket).

### C3. Fast trainer (3–5 Nov, 2 days)
- `lab/cfr/fast/mccfr.py`: external-sampling MCCFR over flat arrays:
  - infoset index = (street, bucket, history id); history ids from a precomputed table of the
    abstract tree (C0's spec, enumerated once; `count_tree.py` grows into `lab/cfr/fast/tree.py`);
  - regrets `float32[n_infosets, max_actions]`, strategy sums `float32[…]`;
  - **Linear CFR / DCFR** weights (α = 1.5, β = 0, γ = 2) and **regret-based pruning** after warm-up
    (actions below −300 M·chips skipped 95% of the time), the Pluribus recipe;
  - parallelism: `numba.prange` over iterations with lock-free ("hogwild") adds; or N processes on
    `multiprocessing.shared_memory`. Measure both on 1 M iterations; keep the faster.
- `lab/cfr/fast/train.py`: CLI with `--hours`, checkpoints every 15 min (np.save of the arrays),
  resume, progress log (`it/s`, % infosets with < 10 visits), export to the existing uint8 format
  plus `float16` for the lab.
- **Validation before any long run** (in this order, each a test or a script with a pass line):
  1. Kuhn in the fast core → −1/18 ± 0.005;
  2. Leduc → exact exploitability below the old trainer's at equal iterations (`lab/cfr/exact.py`);
  3. throughput on the real abstraction: **≥ 20,000 it/s on the laptop**, otherwise stop and simplify
     (fewer buckets, tiny menu) before C4. Record the number in `docs/reports/TIER4.md`.

### C4. First real training run (4–6 Nov, overnight ×2)
- Run 1 (night of 4 Nov): lean menu, buckets 1755/100/100/50, 10 h. Expect ~10⁹ iterations if
  the C3 target holds (estimate).
- Diagnostics every hour: % infosets visited < 10 times (must fall under 5% for the streets you
  ship), average-strategy entropy per street, exploitability *inside the abstraction* by a
  best-response pass (C3's tree makes this a single traversal).
- Export → `data/discard_holdem/blueprint_v1.npz`, embedded as `ARTIFACTS["blueprint"]`
  (`tools/embed_data.py` gains the entry; `bot/artifacts.py` already checks the spec hash).

### C5. The Tier 4 brain (4–6 Nov, 2 days, parallel with C4)
- `bot/cfr/blueprint.py`: decode the table once at start-up (inside the 5 s start budget, not
  charged); `lookup(key) -> probs | None`.
- `bot/brains/tier4.py`: `class Tier4Brain(Tier3Brain)` overriding `play()` only:
  1. endgame lock → as Tier 2/3;
  2. discard → Tier 3/Tier 2 PIMC discard (unchanged);
  3. betting: rebuild the abstract history with `observed_label` (pseudo-harmonic translation),
     compute the bucket, look up; if found and the street is enabled (`cfr_streets` param),
     sample an abstract action with the seeded RNG and map it to chips with the shared rounding;
  4. anything else → `super().play()` (Tier 3).
  - `stats`: hits, misses by reason, translations, time per lookup.
- Register `tier4` in `bot/main.py:BRAINS` (not default).
- **Tests**: runtime key == trainer key on 1,000 random hands (extend `tests/test_cfr_runtime.py`);
  `cfr_streets=[]` reproduces Tier 3 exactly; package builds with `--brain tier4` and passes every
  check (§7 fixes the packager first).

### Gate A (6 Nov) — the kill gate
`lab.eval tier4:{"cfr_streets":[0,1]}` (preflop + flop from the blueprint):
- vs **Tier 3** head-to-head, 100 pairs, lock on: match score > 0.5 **and** chips/hand not worse by 2 SE;
- vs the training pool + starter + sparring, 50 pairs: `--compare` against `tier3` says KEEP or neutral;
- timing ≤ 50% at 2×; memory < 500 MB.

**If gate A fails: stop Track C.** Write the numbers into `docs/reports/TIER4.md`, and all
remaining time goes to Track X and the loop. Three failed fixes in a row also stop it (`CLAUDE.md`).

### C6. More streets (6–9 Nov)
- Enable turn (`cfr_streets=[0,1,2]`), then river, each with gate A's test against the previous best.
- Second training run with whatever C4 diagnostics asked for (more flop buckets, prune the 4th raise).

### C7. Optional: live river solver (7–10 Nov, only if the river line loses)
- Trigger: `lab.opps.accounting` shows the blueprint river losing at river showdowns.
- `bot/cfr/river.py`: vector CFR+ over the ≈ 903-hand river (book §1.7.6), `O(n)` sorted showdowns,
  2–3 sizes + all-in, our range from the blueprint, opponent range from `Opponent.range_weights`
  **adjusted by the exploit layer's type** (a value-only bettor's betting range is value);
  time-boxed by the budget (≥ 50 iterations or fall back to the blueprint).
- Tests: equals `lab/cfr/exact.py` on toy rivers; never exceeds budget in `tests/test_timing_slow.py`.

### Gate B (9 Nov)
Tier 4 (best street set, ± river solver) vs Tier 3 head-to-head 100 pairs > 0.5 by 2 SE, and the
training pool not worse.

### C8 / M1. Merge with the exploit layer (9–11 Nov)
- `Tier4Brain` uses `ExploitLayer` (X3) on its action probabilities, RNR-style (book §1.9.2):
  `p_out = (1 − λ)·p_blueprint + λ·p_counter`, where `p_counter` comes from the same move list as X3
  (e.g. over-folder: move bet mass from check to the smallest profitable bet).
- Gate C: `tier4x` vs `tier3x` head-to-head and on the pool (`--compare`), 100 pairs, fresh seeds.

### M2 / SHIP (11–13 Nov)
- Candidates: `tier4x` (if A, B, C passed), else `tier3x` (if X passed), else `tier3`.
- Ship gate (all on fresh seeds): head-to-head vs the current default > 0.5 by 2 SE; training pool
  `--compare` KEEP; one `--final` run on a **new** held-out set (2–3 fresh LLM bots, picked before results);
  timing at 400/60 s and 1000/150 s ≤ 50% at 2×; memory < 500 MB; zip ≤ 5 MB; `tests` green.
- Package with the explicit brain (`--brain <name>`), record in `docs/SUBMISSIONS.md`, hand to the user
  on 13 Nov evening.

---

## 5. Day-by-day

| Day | Track X | Track C | Gate |
|---|---|---|---|
| Fri 31 Oct | X0 recorder → `lab/opps` | C0 spec draft | — |
| Sat 1 Nov | X1 traits | **Phase H** (Problem Statement) · C0 freeze · C1 start | rules re-check |
| Sun 2 Nov | X1 tests · X2 start | C1 game core · C2 buckets | — |
| Mon 3 Nov | X2 type posterior | C1 equality tests · C3 start | — |
| Tue 4 Nov | X3 moves | C3 validation (Kuhn, Leduc, it/s) · **C4 run 1 overnight** · C5 start | throughput ≥ 20k it/s |
| Wed 5 Nov | X3 | C5 brain + key test · C4 diagnostics | — |
| Thu 6 Nov | **Gate X** | **Gate A** | kill or continue |
| Fri 7 Nov | X4 loop starts (overnight) | C6 turn · run 2 overnight | — |
| Sat 8 Nov | X4 | C6 river · C7 decision | — |
| Sun 9 Nov | ship `tier3x` as upload #5 if gate X passed | **Gate B** | — |
| Mon 10 Nov | X4 | C8 merge | — |
| Tue 11 Nov | — | **Gate C** | — |
| Wed 12 Nov | ship-gate runs | ship-gate runs | — |
| Thu 13 Nov | **freeze**, package, `SUBMISSIONS.md` | | **SHIP** |
| Fri 14 Nov | user uploads; spare day | | |

---

## 6. Risks and their answers

| Risk | Sign | Answer |
|---|---|---|
| Trainer still too slow | C3 < 20k it/s | tiny menu (1 bet size), fewer buckets; or stop Track C |
| Abstraction error (the 2026-10-25 failure) | blueprint loses to Tier 3 despite low in-abstraction exploitability | more postflop buckets; deploy only the streets that win (preflop+flop) |
| Runtime bucket cost | > 15 ms per decision | embedded precomputed flop table; fewer turn samples |
| Off-tree bets from LLM bots | translation rate > 10% in `stats` | add the size they use most to the menu, retrain |
| Rule change on 1 Nov | Phase H | spec-driven fast core; rerun C1 tests |
| The exploit layer misfires | CUSUM alarms often; losses vs adaptive bots | λ ramp slower; `d_new_exploiter` is in the training pool to test exactly this |
| Overfitting to Claude-written bots | gains on the pool, not on fresh bots | new held-out bots from other model families; starter bot in every gate |
| Time | any gate late by > 1 day | drop the latest optional step (C7 first, then C6 river) |

---

## 7. Packaging bug (found while writing this, 31 Oct; fixed the same day)

`tools/package_submission.py` defaults to `--brain tier2` and patches `DEFAULT_BRAIN = "tier2"`
in `bot/main.py`, but `main.py` now says `DEFAULT_BRAIN = "tier3"`. With the documented command
(`--zip --stage2`, no `--brain`) the packaged bot asks for `tier3`, which was not packaged, and
falls back to **Tier 0 (check/fold)**; the package checks then fail ("tier2 exited"). Building with
`--brain tier3` works. **Fixed**: `--brain` now defaults to `bot.main.DEFAULT_BRAIN`, the line is
patched by regex (the build fails loudly if it can't be), and `tests/test_day1.py` checks that the
packaged `main.py` names the packaged brain. Tier 3 built this way passes every package check
(2x bank 32–39 %, 41 MB).

---

## 8. Files

| New (lab) | New (bot, shipped) | Changed |
|---|---|---|
| `lab/opps/record.py`, `lab/opps/traits.py` | `bot/strategy/traits.py`, `bot/strategy/types.py` | `bot/opponent.py` (feed traits) |
| `lab/cfr/fast/{game,eval7,buckets,tree,mccfr,train}.py` | `bot/brains/exploit.py` | `bot/abstraction.py` (v2 buckets, lean menu) |
| `docs/cfr/ABSTRACTION_V1.md` | `bot/cfr/blueprint.py`, `bot/brains/tier4.py` | `tools/embed_data.py` (`blueprint`, `types`) |
| `docs/reports/TIER4.md` | `bot/cfr/river.py` (only if C7) | `bot/main.py` (register `tier3x`, `tier4`) |
| tests: fast-core equality, bucket twin equality, key equality, traits, types, exploit moves, timing | | `tools/package_submission.py` (§7) |

## 9. Later, only if time remains

- The discard as a CFR decision (a private action whose result is public), instead of D3's fixed policy.
- A vector (public-chance-sampling) trainer on your GPU for finer buckets.
- Safe subgame solving for the river (gadget), if the unsafe solver gets exploited in the lab.
