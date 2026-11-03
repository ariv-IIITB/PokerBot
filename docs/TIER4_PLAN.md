# Tier 4 plan (v5, 2026-11-02, after four santa review rounds)

**Running it:** this plan is split into one-session sub-plans in `docs/tier4/` (start with `docs/tier4/README.md`).

At `main` = `795e3a0`. Build on a branch **`tier4/main` cut from `origin/x/exploit-layer`** (`43df7e8`: X1 traits,
X2 type posterior, X3 λ-layer `tier3x`; not merged into `main`). First commit on it: merge `main` (brings this
plan, `PHASE_H_PLAN.md` and the Problem Statement). Phase H runs in parallel in a Sonnet session; merge `main` again
when it lands (expect conflicts only in `bot/main.py` and the generated `bot/embedded.py`: regenerate it with
`tools.embed_data`, never hand-merge).

**This plan supersedes `docs/CFR_BUILDMAP.md` §3 from X4 on** (league tuning and "ship `tier3x` by 9 Nov"). Gate X
moves to Tue 3 Nov night. Track C (§4) is the teammate's, independent until 10 Nov; merging it is **Tier 5**. Our
files never go under `bot/cfr/` (the teammate's C7 also plans `bot/cfr/river.py`); we own the live river solver,
and the teammate is told so.

**Tier 4 = Tier 3 + one counter-strategy per opponent family, chosen by the type posterior + a live river solver +
better use of the discard.** Tier 3 is the fallback inside every decision. Brain name `tier4p` (`tier4` is the CFR
brain). Training bots (`lab/opps/discard_pool.json`): conv_opp3, rules, lag, trapper, exploiter, minraise. Held-out
bots (conv_opp4, eqrandom, geometric): never tuned on, two `--final` runs on 9 Nov (incumbent and `tier4p`, same seeds).

**Measured numbers used below:** throughput 96–579 hands/s across the machine, slowest for exploiter (96),
trapper (151), conv_opp3 (209) (`logs/g/recheck/`). Head-to-head SE between near-identical brains is ~0.02 chips/hand
at 100 pairs (`h2h.txt`, tier3 vs tier2 +0.28 ± 0.02). Pool SE per bot is ~0.08–0.24 at 50 pairs (the SE of a *difference* in `--compare` is ~0.11–0.35). The 80 ms hard
deadline already fires a few times per run (5 in `logs/g/recheck/stderr.txt`, across the tier2 and tier3 runs).

**Every pool gate is two-part:** `lab.eval --compare` KEEP on chips from a **locks-off** run (sum up, no bot down
> 2 SE; the endgame lock flattens chips: Tier 3 vs lag is +0.07 locks on vs +5.18 locks off) **and** the mean
match score from a **locks-on** run not lower by > 2 SE (chips and score diverge: `pool_t3.txt`, conv_opp3 −1.87 chips at
0.48 score). **Every KEEP is confirmed once on fresh seeds** before it counts.

---

## P. Counter-strategy portfolio

**The idea (Hyperborean, Bard et al. 2013):** a portfolio of strategies, each strong against one kind of opponent.
Hyperborean chose members by importance-sampling (IS) estimates of each member's value. **It can't here:** our
per-hand SD is ~30–50 chips, so after 400 hands a member's SE is ~2 chips/hand while member edges are 0.2–2
(`docs/reports/TIER3.md`). Limit hold'em, where Hyperborean ran, has far lower variance. So members are **chosen by
the X2 type posterior**, and IS is a later, optional bail-out (P4).

### P0. Baselines and recordings (Tue 3)
- **P0a:** gate X (`docs/CFR_BUILDMAP.md` §3): `tier3x` vs `tier3`, training pool, 50 pairs, locks on, against
  `logs/g/recheck/pool_t3.txt`. That is the incumbent number P must beat.
- **P0b:** re-record (`lab.opps.record`; `logs/records/` is not on this machine) **12 fresh-seed pairs (24 matches) per training
  and sparring bot, seeds 9000–9011** (`--first-seed 9000`; 100–123 and most low blocks were used before, see
  `docs/reports/TIER3.md`). Used by the detection gate, D0, D2 (fit 9000–9005, score 9006–9011), D4 and R's per-type fits; never for tuning P1. Change
  `record.py` first (lab side only) to save **the opponent's dealt 3 cards on every hand**, not only at showdown;
  D0 needs them.

### P1. Members, one per X2 family (Wed 4)
X2's families are disjoint (`docs/reports/TRACK_X.md` on the branch): over-folder (exploiter, conv_opp3, rules),
value-only (minraise), nit (tight), station (starter = calling_station), trapper (trapper), aggressor (lag, maniac),
unknown. Members are parameter overrides on Tier 3, applied through the `exploit.adjust` mechanism (a pure function
over `adjusted()`'s dict):

| member | X2 family | direction | starting values |
|---|---|---|---|
| `base` | unknown, nit, station | Tier 3 as shipped (stations already lose every match to it, +19–22 chips/hand, and the tie-break clips at C, so a station member has no upside) | — |
| `anti_folder` | over-folder | bluff far more, smallest size whose break-even fold rate is below theirs; fold bluff-catchers to their river bets **only when the posterior's implied river bluff share is ≤ `x_vo_cut` (0.10)**: true for exploiter and rules, false for conv_opp3 (0.23 in `types.json`) | X3's over-folder move at λ = 1, plus X3's value-only move under the same bluff-share condition (= what `tier3x` does) |
| `anti_value` | value-only, trapper | fold bluff-catchers to river bets and raises; fold medium hands to a trapper's raises | X3's value-only move |
| `anti_aggro` | aggressor | call down wider, fewer bluffs | new |

**Tuning (the "restricted" part of RNR, measured, not solved), Wed 4 night:** per member, ≤ 3 parameters × 3
values (≤ 27 points), 16 pairs per point against its family's training/sparring bots. The best 2 points get a
**50-pair confirmation on fresh seeds** (winner's curse). Constraint: head-to-head vs Tier 3 at 50 pairs not worse
than −0.10 chips/hand (≈ 3 SE) and match score ≥ 0.5 − 2 SE. Compute: the grid runs once per bot in the family
(`anti_folder`: exploiter at 96 hands/s, conv_opp3, rules ≈ 1.3 M hands ≈ 2 h; the other members ~0.5 h each);
the head-to-head constraint runs only on the 2 confirmed points. ≈ 4–5 h in all: one night.

### P2. Selection and bail-out (Thu 5)
- Per hand: let F be the family with the highest posterior mass (summed over its types). Play F's member when
  - mass(F) ≥ 0.8 for the last 20 of our decisions, **and**
  - where X1 has a test for that trait, it says yes: the over-folder SPRT for `anti_folder`. For `anti_value` and `anti_aggro` (no X1 test exists) require ≥ 60 opponent decisions seen
    (X3's value-only ramp).
  Otherwise play `base`.
- **Bail-out:** where an X1 CUSUM exists (over-folder), its alarm sends play to `base` and blocks that member
  for 50 hands. For every member: a stop-loss. If our net chips over the hands since the member switched on are
  below 0 by more than 2 SE (per-hand SD measured in this match), play returns to `base` for the rest of the match.
  (Without P4 we can't estimate what `base` would have won on those hands, so the reference is break-even.)
  It is checked only at 25/50/75 % of `total_hands` (hands 100/200/300 in Stage 1), which limits the repeated looks
  to three. At ~4 chips/hand SE by hand 100 it only catches large losses; that is its job.
- **Safe-exploitation spirit** (Ganzfried & Sandholm 2015): the stop-loss limits what a wrong read can cost. It is a
  heuristic, not the paper's guarantee, which needs the game value.
- **Endgame lock** as today, before the portfolio.

### Gate P (Fri 6–Sat 7)
- **Detection on fresh seeds** (P0b's recordings, never used to build `types.json`): over hands 200–400, the right
  member plays ≥ 70 % of hands against each training/sparring bot, and `base` plays ≥ 90 % of hands against
  random_legal and all_in (style outside the library).
- **Each member vs Tier 3**, member forced on: 50 pairs head-to-head, not worse than −0.10 chips/hand and match
  score ≥ 0.5 − 2 SE (cheap to punish = rejected).
- **vs the incumbent:** `tier4p` vs `tier3x` (or `tier3` if gate X failed): head-to-head 100 pairs, match score
  ≥ 0.5 − 2 SE; training pool two-part KEEP (sum up, no bot down > 2 SE). Where a member differs from what
  `tier3x` does (the tuned values, `anti_aggro` vs lag), that bot must be up by > 2 SE; elsewhere, not down.
- **Live detection:** in the pool run, `lab.eval --report stats` counts which member played each hand. Same ≥ 70 %
  rule as the offline check (exploiter adapts to our style, so offline replays aren't enough).
- **Adversary:** a lab bot that over-folds for 100 hands, then calls everything. 50 pairs; lose no more than `tier3`
  does + 2 SE.
- **Stage 2:** one 1000-hand pool run (30 pairs), two-part KEEP.
- Timing and size: add `tier4p` cases to `tests/test_timing_slow.py` (today it hardcodes tier2/tier3): 400 hands / 60 s and
  1000 / 150 s at 2× slower, vs calling_station and trapper (high showdown rates). ≤ 50 % of the bank; deadline hits ≤ the
  Tier 3 baseline + 2√baseline over the same hands; `lab.memory_check` < 500 MB; `tools.package_submission --zip --stage2
  --brain tier4p` passes. Pass → **upload candidate**.
- **If gate P fails:** `tier4p` is shelved for Tier 4. The incumbent (`tier3x` if gate X passed, else `tier3`) is the
  base for D and R: their gates compare the incumbent with vs without each piece, and the incumbent (plus any KEEPs)
  is what ships on 10 Nov.
- Add `tier4p` to `LOCK_BRAINS` in `lab/eval.py`, or `--locks off` silently keeps its lock.

### P4. IS bail-out: **dropped** (no sub-plan builds it; kept here for the reasoning)
- **Go/no-go:** a power calculation. Inputs: the per-hand SD of our net chips Δ from `logs/g/recheck/`, and the fraction
  f of hands where two members act differently at least once (run `base` and a member side by side on the same
  decisions, log both choices, play one). With a 50/50 per-hand mixture (which halves a member's edge while it explores: count that cost
  in the go/no-go), the difference estimator
  `Σ_hands (w_k − 1) · Δ` has SE ≈ SD · √f / √n. **Go only if power ≥ 0.8 at hand 400 for a 2-chip edge**, with
  Holm over the members and alpha split over the three checkpoints.
- If go: refactor Tier 3 into `policy(situation, params) -> [(Action, prob)]`. Today it mixes through ~20 coin-flip
  and state sites (`self._chance`, `_line`, `_floated` in `bot/brains/tier3.py`) plus Tier 2's random size choice.
  Per-hand state is passed in, not mutated. Test: one member, same seed → same actions as before.
  The behaviour policy is a per-hand mixture over members. Weights are clipped at 20, and the bias is stated in the report.

---

## D. The discard

Today: our discard is sampled and importance-weighted by inference (`bot/sim/discard.py` `choose_discard`, given
`opponent.model`). The opponent's hand is weighted by a "sensible discard" softmax (`bot/sim/inference.py`,
`beta`, scaled by `Trust.level("discard")`). The fixed part is their **keep rule**, `opponent_keeps`
(`bot/sim/discard.py:52`): keep the pair that makes the best 5-card hand with the flop, ties to higher ranks.
Gap found 2 Nov: **flop equity rollouts discard at random for both players** (`smart_rollout_discard` off,
`bot/sim/rollout.py`). Note: "60–68 % discard their lowest card" (book §2.8) doesn't show that LLM bots discard
badly: Tier 1 and 2 also show 61 %, because the best keep often drops the lowest card.

### D0. Is there anything to learn? (Wed 4, offline, on P0b's recordings)
For each training bot, which of these rules matches its discards: `opponent_keeps` (the baseline),
`drop_lowest`, `keep_pair`, `keep_flush_draw`, `keep_straight_draw`, `random`. Also how often each rule disagrees with
`opponent_keeps` on that bot's real deals. **Go for D2 only if** some training bot's discards disagree with
`opponent_keeps` on ≥ 15 % of its hands *and* one rule from the list explains ≥ 80 % of them.

### D1. Flop equity with real discards (Wed 4 code · Thu 5 night grid)
This tests a hypothesis, not a fact: Phase E's smart rollouts lost 1.3 ± 0.4 vs tier1 (Tier 2, 30 pairs), perhaps because
the thresholds were tuned on random-discard equity. On Tier 3: (a) smart rollouts on, no retune; (b) plus a 3 × 3 grid
on `raise_equity` × `call_margin`. 30 pairs per point on the training pool + tier1 + tier2, then the best point at
50 pairs on fresh seeds: two-part KEEP. Timing re-checked (pure-Python `_best_discard` per rollout). A D1 KEEP goes into `tier4p` (and the
incumbent) before gate P's runs on Thu night; later D KEEPs are added after gate P, each with its own gate.

### D2. Learn their keep rule (Fri 6, only if D0 went)
- A posterior over D0's rules, updated at each showdown after a discard, when all 3 of their cards are known.
  Noise floor 10 %; the prior per X2 type comes from D0's rule mix, fitted on P0b's seeds 9000–9005, scored on 9006–9011.
- Feeds `inference.py`'s discard likelihood: the rule mixture replaces the fixed softmax.
- Selection bias: only showdown hands are seen. Measure the posterior's accuracy with showdown-only data vs all
  data on seeds 9006–9011.
- Gate: on seeds 9006–9011, the log-likelihood of their shown turn hand is better by > 2 SE. Then 50-pair two-part KEEP.

### D3. Our discard against their keep rule (Sat 7)
- `choose_discard` lets the opponent keep by D2's rule (else `opponent_keeps`).
- Spend more only if it pays: `special_budget_frac` (0.8 of the decision budget today) at 0.8 / 1.5 / 3, measured in
  `lab.eval` (two-part KEEP, 50 pairs), not `lab.discard_bench` (that bench has no betting and no ranges).

### D4. Do they read our discard? (Sat 7, measurement)
Per training bot, on P0b's recordings: turn fold rate by the rank of the card we discarded (low/mid/high), chi-square
test, p < 0.01 with Holm across bots. Only a bot that passes gets an A/B: among near-equal discards, choose by the
signal we want (`hide_discard` is off today).

Every D result, kept or dropped, goes in `docs/reports/TIER4_DISCARD.md`.

---

## R. Live river solver (Fri 6 spike · Sat 7–Sun 8 build · Mon 9 gate)

**Budget.** A decision gets ~4.5–5.4 ms (`bot/timing.py`: 0.9 × 60 s / 400 / 5.5 / 5.5, capped at 1.2× the pace).
The hard deadline is max(80 ms, 6 × budget), and after it `bot/main.py` falls back to **Tier 0**. Tier 3 uses
26–34 % of the bank at 2×, so the headroom to 50 % is 9.6–14.4 s of server time. River decisions per match: ~25 % of hands reach a river
action vs conv_opp3, ~42 % vs trapper (accounting), i.e. up to ~170 per 400 hands. So the river time box is
**wall-clock = 4 × `timer.budget()`, clamped to ≤ 20 ms** (shrinks as the bank drains; ≈ 20 ms laptop, so ~half the
iterations on the 2× server), checked against trapper.

- **R0 spike (Fri 6, go/no-go).** If the full version misses the target, try the reduced one before giving up:
  prune combos with near-zero weight (often < 300 left), one showdown ranking per river shared by all terminals,
  sizes pot + all-in only, warm start from Tier 3's river policy. Exploitability is measured with a vector best
  response inside the solver (`lab/cfr/exact.py` only on reduced-deck toy rivers). Full version: NumPy vector CFR+ over ≤ 903 hands, ~20 nodes, sizes ½ / pot / all-in, ≤ 2 raises.
  Showdown and fold values in O(n) with card removal (sorted hand ranks plus per-card sums). **Go if ≥ 50 iterations
  fit in 10 ms on this laptop** (≈ 20 ms on the 2× server), **including building both ranges**, and the strategy's
  exploitability on toy rivers, computed by `lab/cfr/exact.py`, is ≤ 2 % of the pot.
- **R1 (Sat 7):** `bot/strategy/river_solver.py`, **anytime**: range building and iterations sit inside one time box
  that returns the current average strategy before the river budget. Any error or < 20 iterations → Tier 3's river.
  `TimingConfig` gets a river budget (`river_budget_s`). Re-check that the hard deadline (6 × budget) still covers
  it; the 80 ms alarm must not fire in `tests/test_timing_slow.py`.
- **Our range (new, Sat 7; an approximation and the main risk of an ungadgeted re-solve):** `OwnRange` gives only a
  percentile from our preflop line. Needed: weights over our
  2-card combos from our line on every street and our public discard, using the likelihood model inference uses for
  the opponent. Sensitivity check: if solver EV changes by > 20 % of the pot with our range flattened, the own range is
  treated as the weak point and gate R is read with that caveat.
- **Their range:** score the ≤ 903 combos directly with `Inference.log_weights` (the discard is known by the river),
  plus D2's keep rule if it shipped. This is part of R0's "including building both ranges".
- The solve starts at the current node with the real bet amounts, so off-tree sizes and a 3rd/4th raise are handled.
  In RNR the model player and the free player reach a mid-river root with different ranges; start with both equal to
  the inference range and note it as a simplification.
- **Restricted (Sun 8; RNR on the river, after Milec et al. 2024's CDRNR):** a hidden coin makes the opponent the model
  player with probability p, otherwise a free player solved by CFR+. The model player's per-hand P(fold / call / each
  size) comes from `inference.py`'s bet model (logits γ × (strength − pivot)) with a pivot and γ per X2 type, fitted
  offline on training recordings. p is set as 0.5 × the family posterior mass (a starting rule: posterior mass is
  confidence in the *family*, not in the model being exact). p = 0 is the plain solve; A/B p = 0 vs the rule.
  Caveat: this re-solves the river alone with inferred ranges and no safety gadget, so it isn't safe in the paper's
  sense. Gate R is the check.
- All members use the solver on the river; members differ on earlier streets and in p.
- **Accounting SE (Sat 7, lab):** extend `lab.opps.accounting` to report each bucket's chips/hand with an SE over pairs,
  so gate R can test river showdowns.
- **Gate R (Mon 9):** run with the time box halved (to stand in for the 2× server). `tier4p` with vs without the
  solver: head-to-head 100 pairs, match score ≥ 0.5 − 2 SE; pool two-part KEEP; net of **all river buckets together** (showdown + we fold + they fold; showdown alone can be
  gamed by folding more) vs conv_opp3 and exploiter better by > 2 SE; the restricted-p A/B kept only by its own
  head-to-head + two-part KEEP; **combined timing** (Tier 3 + R + D3's budget, measured together, at 2×) ≤ 50 %; deadline hits ≤ baseline + 2√baseline
  (the same rule as gate P). Fail → drop R.

---

## Timeline (one person + Claude sessions; evals one at a time, grids at night)

| day | day work | night |
|---|---|---|
| Tue 3 | branch + merge main; `record.py` change | P0a gate X, then P0b recordings (one after the other) |
| Wed 4 | P1 members; D0 fit; D1 code | P1 tuning grids |
| Thu 5 | P2 selection + bail-out | D1 grid |
| Fri 6 | gate P detection + member checks; R0 spike; D2 if D0 went | gate P incumbent + adversary + Stage 2 runs |
| Sat 7 | gate P verdict → upload candidate; R1 + own range; accounting SE; D3, D4 | D2/D3 evals |
| Sun 8 | R restricted p; D keep/drop decisions | gate R runs |
| Mon 9 | gate R verdict; held-out `--final` once | final pool run |
| Tue 10 | report, upload candidate, hand off to Tier 5 | — |

**Slip rule:** the source of truth is `docs/tier4/README.md` ("Slip rule"), and I1's retry rule is in
`docs/tier4/I1_integrate.md`. If R is dropped, the river stays Tier 3's.

## Rules for every step
- Tier 3 is the fallback for errors and missing pieces. Long work is time-boxed inside the brain so the hard deadline
  (→ Tier 0) doesn't fire. Never forfeit.
- Duplicate pairs; two-part KEEP; one fresh-seed confirmation; ± SE; one eval at a time per machine (budgets are
  wall-clock).
- `tests/test_timing_slow.py` after any `bot/` change. Nothing reads files at runtime: new tables (type pivots/γ)
  go through `tools.embed_data`.
- Held-out bots: never tuned on; two `--final` runs on 9 Nov (incumbent and `tier4p`, same seeds). If `tier4p` is below the incumbent by > 2 SE on the
  sum there, the incumbent ships instead.
- Seed ledger: fixtures 0–11; P0b 9000–9011; gate X 8000+; tuning and confirmations each get their own block, written
  in `docs/reports/TIER4P.md` (`TIER4.md` is the teammate's report).
- Stage 2: the stop-loss checkpoints are at 25/50/75 % of `total_hands`; the 1000-hand gate runs the incumbent on
  the same seeds.
- Tooling to write (Wed 4): the adversary bot, and a match-score comparison script (the second half of the
  two-part KEEP; `--compare` only does chips).

## Risks
| risk | answer |
|---|---|
| Selection rests on identity, which is optimistic outside the library | "unknown" → `base`; SPRT or ≥ 60 decisions before a member plays; stop-loss; detection gate includes random_legal/all_in |
| A member is cheap to punish | each member vs Tier 3 forced on, −0.10 chips/hand limit |
| Overfitting to Claude-written training bots | tuning on training bots only; fresh-seed confirmations; held-out `--final` |
| River solver too slow, or worse on the slower server | R0 go/no-go including range building; anytime; gate R with the time box halved |
| D2 has nothing to learn | D0 go/no-go |
| The hard deadline already fires a few times per run | deadline hits ≤ baseline + 2√baseline in gates P and R; the solver is time-boxed |
| Merge conflicts with Phase H / `main` | merge early; regenerate `bot/embedded.py` |
| Collision with the teammate's CFR files | nothing under `bot/cfr/`; we own the river solver |
| Days slip | the slip rule above |
