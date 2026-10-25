# Part 3 — from heuristic to CFR (Tier 3): the approved roadmap

(Condensed copy of the Part 3 brief, kept in the repo so the plan survives between sessions.
`~/Desktop/pokerbots_synergy2` is the main repo since 2026-10-25; the original
`~/Desktop/pokerbots_synergy` is an untouched archive.)

## CFR status (2026-10-25): no-go

**Current plan.** Phase 23 done (`docs/reports/PHASE23.md`). Next: a reduced Phase 24
(tournament simulator with the format in JSON, a <= 300-line hackathon-day bot, a few more
realistic opponents, training/held-out pool split, a tournament-points report; no LBR). Then
the Phase 21 rehearsals with variants we write ourselves. Phases 25-32 are not pursued.
Tier 2 is the bot we ship.

**What we found (Phase 23).**
- The MCCFR solver itself is correct: on Leduc its exact exploitability falls steadily to 0.020
  at 10^6 iterations. But the shipped trembling-hand default (eps = 0.05) biased it: it stalls
  at 0.063. Fixed (default 0).
- The Hold'em abstraction (8 noisy equity buckets; 0.5 pot / pot / all-in) has ~0.9 million
  infosets. After 2 h of training, 75% were still visited fewer than 10 times. Sustained speed:
  ~68 iterations/s on one core.
- Every CFR strategy lost to Tier 2 (51,200 hands each, endgame lock on both sides): the
  best full Hold'em strategy scored -0.29 ± 0.07 chips/hand (37.5% match score). A small,
  well-trained tree (30 bb, 2 raises per round, pot / all-in; 4.3k infosets, median 155 visits)
  still lost: -0.09 ± 0.02 chips/hand (-45 mbb/hand), 34% match score.
- Not the problem: the export (uint8 rounding ~1%), the runtime lookup (0% off-tree), or the
  average-vs-current choice. One runtime labelling bug was found and fixed, but it wasn't
  what lost the matches.

**Why we stopped.** Even the well-trained small tree loses, so more training alone won't fix
it. Beating Tier 2 would need a much faster trainer (Phase 25), a better abstraction
(Phase 26) and the Tier 3 bot (Phase 27) all together. That doesn't fit the time we have
before the reveal. Tier 2 already wins every match against the sparring bots, and its
biggest leak (folding too much to shoves) is fixed.

**What would have to change to reconsider.**
1. A cheap proof first: a better-abstracted small game (for example `holdem_short30` with
   exact preflop classes and finer buckets) that beats Tier 2 on expected tournament points.
   If even that fails, CFR stays off.
2. A trainer that updates orders of magnitude more infosets per second (vectorized public
   chance sampling over all private hands, Phase 25), shown by lower abstract exploitability
   at equal wall-clock time.
3. Evidence from the tournament simulator that Tier 2 loses points to strong,
   equilibrium-style opponents, so there is something for CFR to win.
4. At least a free week before the reveal.

**What stays in the repo.** `lab/cfr/` keeps the MCCFR trainer, Leduc, exact best response,
diagnostics, runtime audit and the CFR brain (`lab/cfr/brain.py`, lab only), plus their
tests. CFR is not in `bot/` or the bot's brain registry, and the submission package never
includes CFR code or strategy files.

**Goal.** A CFR blueprint decides betting; Tier 2 + PIMC stays the fallback and handles
non-betting steps (discards, draws, swaps, bids, quotes). Safe exploitation and a
match-objective layer on top. One referee: **expected tournament points**, guarded by
**exploitability**. Everything trainable **in one night** on this machine.

**Process.** Phase by phase; each ends with all tests green on 3.11 (old ones too), a short
report (built / tests / sustained performance / kill-rule status per variant / what's missing
for reveal day / files changed), a commit `phase N: ...`, then stop for OK. Bot constraints
from `CLAUDE.md` always hold. `lab/` may use optional accelerators (e.g. Numba) but the
pure-NumPy path must work and be tested; nothing in `bot/` may depend on them.

**Machine.** Apple M4 (4 performance + 6 efficiency cores), 16 GB, macOS 15.6.1, fanless
MacBook Air: every throughput number must be a **sustained** rate over >= 30 minutes.

**Open facts.** Data files: assume `.npy` allowed with a 50 MB cap; the bot must work with
no data files (falls back to Tier 2). Seed-bot descriptions for Phase 30 come from the user.

## Approved decisions
- **0.1 Scope.** CFR decides betting only. Non-betting steps use PIMC + inference at runtime;
  in training they're played by a cheap `training_policy` hook whose public outcome multiplies
  each player's reach by the policy's likelihood (documented approximation).
- **0.2 Kill rule (per variant).** Tier 3 is the default only if (1) time and memory gates pass
  (worst decision within budget at 2x slowdown, peak RSS < 600 MB, fast startup); (2) it beats
  Tier 2 on expected tournament points across the training pool (sequential test, Phase 24);
  (3) its LBR exploitability is not worse than Tier 2's. Otherwise ship Tier 2. Computed and
  written down automatically.
- **0.3 One referee.** Expected tournament points (Monte Carlo of the real format); chips/hand
  is secondary.
- **0.4 Hypotheses.** H1 a trained blueprint beats Tier 2; H2 exploitation + match layers add
  points; H3 the pipeline fits in one night.

## Phases (original plan; status in brackets)
- **23 Diagnose the Phase 22 CFR loss.** [done] Leduc + exact best-response exploitability (MCCFR+ at
  10^3..10^6 iterations, must fall to 0); HUNL instrumentation (infosets, sustained it/s,
  visit histogram, % < 10 visits); export check (average vs current, uint8, pruning, float vs
  exported head-to-head); runtime path (off-tree / translation / fallback rates over 50k hands,
  test runtime bucket == training bucket); scale experiment (small tree 30 min; HUNL 30 min vs
  2 h same seed); causes ranked by evidence; fix bugs, re-run the 50k comparison.
- **24 Evaluation upgrade.** [reduced: items 1, 4, 6 only — tournament simulator, opponent
  pool + split, tournament-points report; no LBR, no accept.py] `lab/eval/tournament.py` (pairwise match probabilities -> Monte
  Carlo of Swiss 6x200 + top-32 round robin x500, format in JSON); `action_distribution(view)`
  on every brain; `lab/eval/lbr.py` (Local Best Response, validated on a small game);
  opponent pool in `lab/pool/` (hackathon-day bot <= 300 lines, LBR exploiter, snapshots,
  sparring) split into training and held-out (`--final-check` only); `lab/eval/accept.py`
  (sequential test, LBR cap, no regression vs last 3 champions, ledger
  `results/ledger.jsonl`). Report points + LBR for Tier 1, Tier 2, P22 CFR, hackathon bot on
  HUNL, MIT discard, one auction variant. Tier 2's LBR is the bar.
- **25 Fast CFR trainer.** [not pursued] `lab/cfr/compile.py` (flat NumPy tree + bucket maps),
  `lab/cfr/pcs.py` (public chance sampling, vectorized reach over all private hands, DCFR
  a=1.5 b=0 g=2, alternating updates, export the average), exact vectorized terminal payoffs
  with card removal (verified vs brute force), multiprocessing, checkpoints, ETA, sustained
  throughput >= 30 min. Validate: Kuhn -1/18, Leduc exploitability below old MCCFR at equal
  wall clock, in-abstraction BR curve for HUNL. **Gate:** clearly lower abstract
  exploitability than the old trainer at equal time, else stop.
- **26 Abstraction bake-off.** [not pursued] Lossless preflop, EMD buckets flop/turn, river equity; action
  sets A {0.5, 1, all-in} vs B {0.33, 0.75, 1.5, all-in} with caps; 3-4 configs on the same
  overnight budget; evaluate with Phase 24 tools; HUNL + MIT discard; keep winner + runner-up.
- **27 Tier 3 runtime bot.** [not pursued] `bot/brains/tier3.py` (sample the mixed strategy, pseudo-harmonic
  translation, legal mapping, PIMC for non-betting, Tier 2 fallback), runtime bucketing in
  budget (test runtime == training bucket), uint8 data with pruning chosen by measured loss,
  spec hash, data cap, works with no data; Tier 2 PIMC argmax -> softmax sampling; gates
  (2x timing, RSS < 600 MB, startup, fuzz with/without data); apply the kill rule (H1).
- **28 Safe exploitation.** [not pursued] Opponent-type detectors; abstract best responses vs simple types
  as small tables (or blueprint tilts); bounded mixing weight w <= w_max growing with
  evidence; LBR at w_max under the cap; trust reset. Report training + held-out pools (H2).
- **29 Match-objective layer.** [not pursued] Shared endgame lock for Tier 2/3 (tested at 400 and 1000
  hands, seat alternation); late-match variance control (off by default until it gains
  points); judge by match wins / points.
- **30 Seed bots.** [not pursued] Configs in `lab/seeds/<name>/` from user-supplied descriptions (no copied
  code/tables); Tier A trained as bake-off slots, Tier B on the locked blueprint; ablations;
  transplants through `accept.py`.
- **31 Reveal-day pipeline.** [not pursued] `lab/overnight.py --variant variant/active.json --hours 9`
  (buckets -> compile -> train -> export -> package -> morning evaluation ->
  `results/morning_report.md` with the kill-rule call); docs + packaging for Tier 2-only and
  Tier 3 packages; 1-hour dry run on 2 variants with a projected night schedule (H3).
- **32 (stretch) River re-solving** [not pursued] from Bayes-updated blueprint ranges, adopted only via
  `accept.py`.

**Cut order if time runs short.** Keep 23, 24 (at least tournament sim + LBR), 25, 27, 31;
then 29, 28, 26 (2 configs), 30, 32.

**Non-negotiables.** No regressions (full suite every phase); Tier 2 always a working fallback
in every package; no Tier 3 default without the kill rule; hidden-information correctness
tested (runtime bucketing, LBR range tracking); held-out pool never used for tuning.
