# Phase 23 report — why Tier 2 looked weak vs sparring bots, and why the Phase 22 CFR lost

Machine: Apple M4 (4 performance + 6 efficiency cores), 16 GB, macOS 15.6.1, fanless Air.
Repo: `~/Desktop/pokerbots_synergy2` (a copy; the original repo is untouched).
Raw outputs: `results/audit/`, `results/p23/` (gitignored).

## 0. Baseline
Fast suite 904 passed after one fix (a test assumed no generated `data/holdem_nl/` existed;
it now ignores the repo's data dir). Slow suite 257 passed (18.5 min).

## A. "Tier 2 only scores ~+0.1 chips/hand against some sparring bots"

**Finding 1 — mostly a measurement artifact (the endgame lock).** Once Tier 2's lead exceeds
the blinds it could lose by folding every remaining hand, it check/folds for the rest of the
match. That is right for match wins, but it caps chips/hand at roughly +0.4..+1.4 against
*every* sparring bot. Same bot, same deals (Hold'em, 8 seeds x 2 seats x 400 hands):

| opponent | lock on | lock off |
|---|---|---|
| random_legal | +0.99 ± 0.03 | +30.2 ± 1.1 |
| all_in | +0.45 ± 0.01 | +16.6 ± 1.9 |
| calling_station | +0.87 ± 0.02 | +6.6 ± 0.3 |
| tight | +1.41 ± 0.10 | +5.5 ± 0.6 |
| maniac | +0.56 ± 0.06 | +69.7 ± 1.8 |

Match score is 1.00 in all of these. The lowest lock-on number was **short deck vs all_in:
+0.23 ± 0.11** (and Omaha vs all_in +0.37).

**Finding 2 — a real Tier 2 leak: it folds too much to shoves.** Best possible vs the
always-all-in bot on Hold'em is about **+31.4** chips/hand (call with any hand >= 49.75%
equity vs random; computed from the precomputed equity table). Tier 2 got +16.6. Ablation:
switching off `bet_pressure` (extra equity demanded to call big bets) gives **+31.8** (the
maximum); switching off inference changes nothing. Cause: `bet_pressure` assumes big bets
mean strong hands and never adapts, and the opponent model's aggression stat ignores
preflop, so it can't see a preflop shover. On short deck this cost matches: 81% wins vs
all_in with the lock off.

**Fix (bot/opponent.py, bot/brains/tier2.py, bot/config/tier2.json).** New stat
`aggression_all` (raises / (raises + calls) on every street, shrunk to a 0.35 prior). When
it is above `pressure_aggr_from` = 0.6, `bet_pressure` shrinks linearly to 0 at 1.0. Measured
levels: Tier 2 0.43, Tier 1 0.45, tight 0.40, calling station 0.01 (all untouched),
random 0.79, maniac 0.85, all_in 0.97.

Old vs new, lock off, vs all_in (8 seeds x 2 x 400 hands): Hold'em +16.6 → **+30.7**,
MIT discard +21.6 → **+37.6**, Omaha +5.4 → **+15.4**, short deck +2.2 → **+18.2** (match
wins 0.81 → 0.88), 2-7 lowball +45.8 → **+99.7**, auction +56.1 → **+64.8**, three boards
+14.5 → **+27.2**, FL Hold'em unchanged. The other 32 rows (4 opponents x 8 variants) are
unchanged within noise. New vs old Tier 2 head to head (40 seeds x 2 x 400 hands): Hold'em
lock off +0.34 ± 0.38, lock on -0.10 ± 0.04 (match 0.45 ± 0.06); short deck lock off
+0.04 ± 0.30, lock on +0.12 ± 0.06 (match 0.56 ± 0.06). Opposite signs, consistent with
noise: against normal bots the new code plays exactly as before. An A/A check (old Tier 2
vs itself, lock on, same setup) gives -0.06 ± 0.06 and exactly 0.500 match score, so
differences of ~0.1 chips/hand with the lock on are noise (time-budgeted sampling).

**Finding 3 — the sparring bots are too weak to test anything else.** Tier 2 wins 100% of
matches against all five on all 8 variants (except all_in on short deck). They can't tell
two Tier 2 versions apart. Phase 24's pool (hackathon-day bot, LBR exploiter) is the real
test. Remaining under-exploitation (calling station, tight) is small and belongs to the
Phase 28 detectors.

Tool: `lab/sparring_audit.py` (lock on/off table, `--set key=value` overrides).

## 23.1 Exact convergence on a small game
- `lab/cfr/leduc.py`: Leduc Hold'em (6 cards, raise 2/4, cap 2 per round; 144 + 144
  infosets using ranks only, 9,450 nodes).
- `lab/cfr/exact.py`: game tree + exact expected value, best response and exploitability for
  any tabular policy, and a full-width CFR+ reference solver. Checks: equals the old Kuhn
  enumeration exactly; uniform Leduc policy 2.3736 (the known value); reference CFR+ reaches
  0.0062 after 300 iterations with value -0.0855 (literature: -0.0856).
- Existing MCCFR+ on Leduc (average strategy, exact exploitability, ~1,400 it/s):

| iterations | eps = 0 | eps = 0.05 (trainer default) |
|---|---|---|
| 10^2 | 2.069 | 2.296 |
| 10^3 | 0.683 | 0.809 |
| 10^4 | 0.177 | 0.262 |
| 10^5 | 0.0637 | 0.0836 |
| 10^6 | **0.0197** | **0.0628 (stalled)** |

The solver is correct: with eps = 0 exploitability falls steadily (about T^-1/2). The
trainer's default trembling hand eps = 0.05 samples the opponent off-policy *without*
importance correction, which biases the solution: it stalls at ~0.063. **Fixed: default
eps = 0** (documented in `lab/cfr/mccfr.py`).

## 23.2 HUNL instrumentation (8 buckets, sizes 0.5 / 1 pot / all-in, 200 bb)
| run | iterations | infosets | visited < 10 | median visits |
|---|---|---|---|---|
| Phase 22 (30 min, ~48 it/s) | 86,850 | 839,513 | n/a (not recorded) | ~1.7 (estimated) |
| new, 30 min (eps 0.05) | 38,200 | 743,363 | 93.4% | 1 |
| new, 2 h (eps 0.05) | 165,750 | 888,507 | 75.0% | 4 |
| 30 bb small tree, 30 min | 130,900 | 4,342 | 2.7% | 155 |
| clean run, eps 0, at 38,200 it | 38,200 | 718,498 | 94.0% | 1 |
| clean run, eps 0, 30 min | 121,950 | 852,161 | 82.0% | 3 |

At 2 h by street: preflop 2,537 / flop 29,847 / turn 173,044 / river 683,079 infosets; of these
874 / 10,958 / 104,987 / 549,342 are visited < 10 times. The tree is still growing at 2 h.

Sustained rate (clean 30-minute run, idle machine, one core): **~68 iterations/s**
(121,950 iterations). The per-minute rate climbs from ~50 to ~110 it/s as the strategy
learns to fold and traversals get shorter. The 2-hour run shared the machine with
10-process audits: 20-23 it/s. Leduc: ~1,400 it/s.

## 23.3 Export check
- The **average** strategy is exported (correct), as uint8 summing to 255.
- uint8 rounding: mean L1 change 0.006 per infoset (max 0.031). Negligible.
- Pruning: "uniform" infosets (37.5% of infosets, 7.9% of strategy weight) are dropped, so
  the bot falls back to Tier 2 there. The `--min-weight 50` pruning removed only **0.06%**:
  the weights grow with the iteration number, so it can't detect rarely-visited spots.
  ~425k infosets were shipped, most trained from 1-2 samples. Added `--min-visits`
  (traverser visit counts).
- Average vs current: the shipped *average* strategy -0.55 ± 0.08 vs Tier 2; the *current*
  (regret-matching) strategy from the same checkpoint -0.49 ± 0.07. No better.
- Float (unquantized, unpruned) vs Tier 2: -0.44 ± 0.08; shipped: -0.55 ± 0.08.
  Float vs shipped head to head: -0.92 ± 0.47 chips/hand, match 0.50 (32 seeds). No
  measurable difference: export is not the cause.

## 23.4 Runtime path (Phase 22 strategy vs Tier 2, 51,200 hands, endgame lock on both)
Betting decisions: 65.7% from the table, 34.3% under the endgame lock (Tier 2 path),
**0.0% off-tree** (key missing or action-count mismatch), 0% hand-rebuild failures; 3.2% had
a translated opponent bet in the history.

**Bug found by the new test** (`tests/test_cfr_runtime.py`: at every decision, the bot's key
and abstract actions must equal the trainer's, computed from the engine's true state): when
a pot-fraction raise is clamped to all-in, training labels it "H"/"P" but the runtime
labelled it "A", so the rest of the hand used the wrong infoset. Fixed: past raises are
labelled by exact match against the abstract action list at that point; only true off-tree
sizes are translated. Re-run (same table, 51,200 hands): **-0.55 ± 0.08, match 0.258**
(Phase 22 reported -0.40 ± 0.07, 34%). Within noise: the bug was real but not material.

## 23.5 Scale experiment (vs Tier 2, 51,200 hands each, locks on)
| strategy | chips/hand | mbb/hand | match score |
|---|---|---|---|
| 30 bb small tree, 30 min | -0.09 ± 0.02 | -45 | 0.344 |
| HUNL 30 min (38k it) | -0.67 ± 0.07 | -335 | 0.211 |
| HUNL 2 h (166k it), same seed | -0.41 ± 0.06 | -205 | 0.297 |
| HUNL 2 h, prune < 10 visits | -0.30 ± 0.08 | -150 | 0.344 |
| HUNL 38.2k it, eps = 0 (clean run) | -0.56 ± 0.07 | -280 | 0.250 |
| HUNL 30 min clean, eps = 0 (122k it) | -0.29 ± 0.07 | -145 | 0.375 |
| Phase 22 shipped (87k it) | -0.55 ± 0.08 | -275 | 0.258 |

More training helps: 30 min → 2 h on the same seed gained +0.26 chips/hand (2.8 SE), and so
does dropping undertrained spots. The best Hold'em strategy (clean 30-minute run, eps = 0,
122k iterations) still lost: -0.29 ± 0.07. A smaller tree loses much less per big blind,
but it still loses.

## 23.6 Causes, ranked by evidence
1. **Undertraining: the tree is far too big for this trainer.** 75-93% of infosets seen
   < 10 times; results improve with time and with pruning; river infosets are 77% of the
   tree. This is what Phase 25 (vectorized public chance sampling: every private hand
   updated per iteration) is for.
2. **Abstraction quality.** Even the well-sampled 30 bb tree loses (-45 mbb/hand). Buckets
   come from a 64-sample equity estimate: ~38% of hands land one bucket away from their
   true strength (preflop vs the exact table, flop vs 4,000 samples). Two or three bet
   sizes; Tier 2's 0.66-pot bets need translation in 3-11% of decisions. Phase 26.
3. **Trembling-hand bias (eps = 0.05).** Proven on Leduc (stalls at 0.063 vs 0.020).
   On Hold'em at equal iterations (38,200, same seed): eps = 0 scored -0.56 ± 0.07 vs
   -0.67 ± 0.07 with eps = 0.05 (+0.11, about 1 SE): real but small. Fixed (default 0).
4. **Export pruning didn't prune.** Noisy rarely-visited spots were shipped. Fixed
   (`--min-visits`), modest gain.
5. **Runtime labelling bug.** Fixed and tested; not material.
6. **Not causes:** quantization, average-vs-current, off-tree rate (~0%).

## Decision (user, 2026-10-25): no-go on CFR
Even the well-trained 30 bb tree loses to Tier 2, so fixing CFR would need Phases 25-27
together, which doesn't fit the timeline. Phases 25-32 are not pursued; **Tier 2 ships**.
The CFR code and tests stay in the repo but out of the bot and the package: the brain moved
to `lab/cfr/brain.py` (with `lab/cfr/abstraction.py`) and is registered only in the lab, and
the packager no longer copies `cfr_strategy.json`. Details and what would make us reconsider:
"CFR status" in `docs/PART3_ROADMAP.md`.

## Kill-rule status (per variant)
No Tier 3. The CFR bot fails rule 2 (tournament strength vs Tier 2) on Hold'em and on the
30 bb tree. **Tier 2 ships on every variant.**

## Tests
Python 3.11.17. Final state: fast suite **921 passed** (12 s, `-n auto`), slow suite
**259 passed** (9 min 39 s). The Tier 2 commit on its own: 905 fast tests passed (checked in
a clean worktree). New tests cover:
- Leduc rules and tree size; exact best response vs the old Kuhn enumeration; the known
  uniform Leduc value; the reference CFR+ (Kuhn; Leduc's game value in the slow suite).
- MCCFR improving on Leduc; export pruning by visit count; raise-size parsing; the
  diagnose export kinds; the trainer CLI (snapshots and resume).
- Runtime key == training key at every decision (3 variants).
- Tier 2: all-street aggression counting and the bet-pressure relaxation.
- CFR is lab-only and never packaged.

## Files changed
Commit 1 (Tier 2 fix): `bot/opponent.py` (`aggression_all`), `bot/brains/tier2.py`
(`bet_pressure` scaled down vs very aggressive opponents), `bot/config/tier2.json`,
`lab/sparring_audit.py` (new), `tests/test_tier2.py`.

Commit 2 (phase 23):
- CFR moved out of `bot/`: `bot/brains/cfr.py` → `lab/cfr/brain.py` (exact-match labels,
  `table_key`, decision stats, `strategy_file`, float tables); `bot/sim/abstraction.py` →
  `lab/cfr/abstraction.py` (configurable sizes); `cfr` removed from `bot/main.py`'s
  registry and added to `lab/players.py`'s; `tools/package_submission.py` (no strategy files).
- `bot/sim/replay.py` (legal set in the bet log).
- lab: `cfr/leduc.py`, `cfr/exact.py`, `cfr/diagnose.py`, `cfr/runtime_audit.py` (new);
  `cfr/mccfr.py` (visit counts, eps note, visit pruning), `cfr/train.py` (eps 0, snapshots,
  progress log, sizes, `--min-visits`), `cfr/abstract_game.py` (sizes).
- variant: `catalog/holdem_short30.json` (new).
- tests: `test_cfr_exact.py`, `test_cfr_runtime.py` (new); `test_cfr.py`, `test_day1.py`
  (CFR is lab-only and never packaged), `test_precompute.py` (stops reading generated repo
  data).
- docs: `PART3_ROADMAP.md` (with "CFR status"), `reports/PHASE23.md`, README, CLAUDE.md
  (synergy2 is the main repo).

## When the variant is revealed (unchanged by this phase)
`variant/active.json` (spec), `bot/protocols/` (wire format), step plugins if needed; then
`lab.precompute` on the new spec. The Tier 2 fix is variant-agnostic.

## Missing for reveal day
Reduced Phase 24 (tournament simulator, hackathon-day bot, realistic opponents, pool split,
tournament-points report), then the Phase 21 rehearsals.
