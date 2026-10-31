# Tier 4 (CFR blueprint, Track C): reports

Plan: `docs/CFR_BUILDMAP.md` §4. Branch `cfr/tier4`. Contract: `docs/cfr/ABSTRACTION_V1.md`.

## C0. Specification (2026-10-31)

**What:** `docs/cfr/ABSTRACTION_V1.md`, the trainer/runtime contract: game parameters from the spec,
the lean action menu with exact formulas, rounding (Python half-to-even) and clamping (a size that
lands on all-in is `A`), the history/key format, the integer table layout, the fixed training
discard, the four bucket definitions with a **shared SplitMix64 sampler** (so the NumPy runtime and
the Numba trainer compute identical bucket ids), quantile thresholds shipped inside the blueprint
artifact, the run-time translation rules, and a worked example (one hand, all 12 keys).

`lab/cfr/fast/tree.py` is the executable reference for the betting part: menu, chips, histories,
enumeration and history ids, all parameters read from the variant spec.

**Decision taken here (not in the build map):** an abstraction-only **sized-raise cap of 3** per
street (from the 3rd bet/raise on, only fold/call/all-in). It trims the tree by 13 %; cap 2 is the
fallback if C3's throughput misses 20 k it/s.

**Tree sizes** (`.venv/bin/python -m lab.cfr.fast.tree --count`):

| sized-raise cap | histories pre / flop / turn / river | infosets at 1755/100/100/50 | uint8 table |
|---|---|---|---|
| 4 (engine) | 14 / 176 / 1,444 / 7,776 | 575,370 | 1.55 MB |
| **3 (v1)** | 12 / 132 / 1,196 / 6,964 | 502,060 | 1.37 MB |
| 2 | 8 / 60 / 540 / 3,820 | 265,040 | 0.73 MB |

The build map's estimate (562 k infosets) is confirmed in size; its history counts were lower
(it used another counter, now gone). The river holds ~70 % of the infosets.

**Tests:** `tests/test_cfr_tree.py`, 8 tests: chips, pot, to-call and the legal raise range equal
the rules engine `bot/game` at every decision of 1,200 random lines (caps 4, 3, 2); every
abstract raise amount is legal in the engine; the worked example; rounding and merging; dense
history ids.

**Environment:** `numba==0.62.1` added to `requirements-dev.txt` (lab only). It installs next to
NumPy 2.3.4 without changing it.

**Not done in C0 (by design):** bucket thresholds and the sampled feature values of the worked
example need C2's sampler; C2's test pins them.

## C1 + C2, first part (2026-11-01)

**What:**
- `lab/cfr/fast/eval7.py`: Numba 7-card evaluator. One lookup in a best-of-7 table over the 50,388
  rank multisets (built from `bot/evaluator.py`'s 5-card table) plus the flush suit's 5-subsets when a
  suit has 5+ cards. **Equal to the bot's evaluator on 1 M random hands; 63 ns per hand** (16 M/s;
  a first version allocating per call took 888 ns).
- `bot/abstraction.py` (shipped, NumPy) and `lab/cfr/fast/buckets.py` (Numba): the §5 SplitMix64 sampler
  and the flop / turn / river features. **Bit-identical on 5,000 random situations** (exact integer
  counts, one division).
- `lab/cfr/fast/tree.py: flatten`: the abstract tree as flat arrays for the trainer (22,498 nodes at cap 3);
  terminal payoffs equal `bot/game`'s on 600 random hands.

**Costs (laptop):**

| | flop | turn | river |
|---|---|---|---|
| runtime, NumPy, per decision | 3.2 ms | 0.5 ms | 0.5 ms |
| trainer, Numba, per seat | 0.09 ms | 0.04 ms | 0.02 ms |

The runtime is well inside the 15 ms budget (≈ 6.5 ms at 2× on the flop). A training deal (both seats,
all streets) is ~0.3 ms per core, so the trainer uses a **precomputed deal pool** (contract §5.6):
~10 M deals in ~5 min on 10 cores.

**Design change vs the build map:** no Numba betting state machine. The betting tree is the same for
every deal, so C3 walks `tree.flatten`'s arrays; the per-deal work is the pool's buckets and showdown.

**Tests:** `tests/test_cfr_fast.py` (7 fast + 2 slow), 3 new flat-tree tests in `tests/test_cfr_tree.py`.
Fast suite 1214 passed, 2 skipped; slow twin tests passed.

**Next (C2 rest, C3):** the deal pool builder with the fixed discard (§4); fit the §5.5 thresholds on
200 k pool deals and pin the worked example's bucket ids; then the MCCFR traversal over the flat tree and
the 20 k it/s throughput check.

## C2, second part: deal pool and thresholds (2026-11-01)

- `lab/cfr/fast/deals.py`: reproducible deals (SplitMix64 from pool seed and index), both seats discard by
  the fixed policy, exact integer features per seat/street and the showdown result; `numba.prange` over deals.
  **16,000 deals/s** on 10 cores (10 M in ~10 min). Pool files go to `data/cfr/` (not in git).
- `lab/cfr/fast/cuts_v1.json`: §5.5 cuts fitted on 200,000 deals. Flop/turn: all 100 cells used, 3,985–4,017
  each; river: 25 equal HS bins, the blocker bit is the rarer half.
- Worked example buckets: button 93 / 89 / 40, big blind 80 / 74 / 32 (now in the contract's §6).
- Tests: `tests/test_cfr_deals.py` (5): pool features == runtime features with the training discard, classes,
  showdown; equal-mass cells on a fresh pool; vectorized bucket ids == runtime bucket functions; the example.

**Next (C3):** MCCFR over the flat tree with the pool (validated on Kuhn as a flat tree), throughput vs 20 k it/s.

## C3. Fast trainer (2026-11-01)

- `lab/cfr/fast/mccfr.py`: external-sampling MCCFR over the flat tree, deals drawn from the pool; regret
  matching; iterations in parallel without locks (`numba.prange`, "hogwild"); Linear CFR by discounting
  regrets and strategy sums by t/(t+1) after each of the first N batches; per-row traverser visit counts;
  exact profile value / best response / exploitability over an enumerated set of deals; uint8 export
  (rows visited < `min_visits` times are zero = miss at run time).
- `lab/cfr/fast/train.py`: CLI with `--hours`/`--iters`, checkpoints every 15 min, `--resume`, progress log,
  blueprint export (`blueprint_v1.npz`: `probs` uint8 [502,060 × 6] + `meta` JSON with version, spec hash,
  params, cuts, history strings).
- `lab/cfr/fast/toy.py`: Kuhn poker as a flat tree.

**Validation (build map C3, in order):**
1. **Kuhn:** value −0.0555 (exact −1/18 = −0.0556), exploitability 0.0014 after 200 k iterations. Pass.
2. Leduc: not done (Kuhn plus the exact checks of the flat tree against `bot/game` cover the traversal;
   Leduc would add a public card, which the real tree already exercises). Skipped on purpose.
3. **Throughput on the real abstraction** (cap 3, 502,060 rows, real buckets): **240 k it/s on one thread,
   1.2–1.35 M it/s on 10 threads**, ~60× the 20 k it/s gate. **Cap 3 stays** (decision 2 of 1 Nov).

Note: Numba's on-disk cache segfaulted when it loaded the self-recursive traversal compiled in another
run; the traversal and its callers are compiled per run (`cache=False`, a few seconds).

**Tests:** `tests/test_cfr_mccfr.py` (4): Kuhn value and exploitability; uniform-profile exact values; a
smoke run on the real tree (finite regrets, average strategy sums to 1 on legal actions, export rows sum to
255 or 0); the CLI end to end with checkpoint, resume and export metadata.

## C5. The Tier 4 brain (2026-11-01)

- `bot/cfr/blueprint.py` (shipped, NumPy): `Blueprint` (the uint8 table + metadata; refuses another contract
  version), `abstract_view` (replays the hand's betting on real chips with the contract's menu formulas; exact
  menu sizes keep their label, other raises are translated pseudo-harmonically, a sized raise past the cap is
  a miss), `menu`, `bucket` (preflop class; flop/turn/river features + the blueprint's cuts).
- `bot/brains/tier4.py`: `Tier4Brain(Tier3Brain)` overrides `play()` only. On a street in `cfr_streets`
  (default `[0, 1]`) it samples the blueprint's action and maps it to chips on the real state; everything else
  (discard, other streets, off-tree history, untrained row, a replay that disagrees with the engine's to-call
  or stack, a budget under 10 ms, any error) goes to Tier 3. The endgame lock is handled before `play()`.
  Registered as `tier4` in `bot/main.py` (**not the default**).
- `lab/cfr/fast/brain.py`: `tier4lab` = Tier 4 with a blueprint file (`blueprint_file`), since the bot itself
  may not read files. Embedding the blueprint as `ARTIFACTS["blueprint"]` waits for a blueprint that passes gate A.
- Known limit: when Tier 4 plays preflop, Tier 3's own-range line model (used by its postflop fallback) does
  not see those preflop actions.

**Tests:** `tests/test_tier4.py` (9): runtime key and menu == trainer's at every node of 1,000 random lines per
seat; translation and cap misses; the worked example's buckets through the runtime path; artifact round trip
and version check; with a small trained table, legal matches vs calling_station, maniac and tier1 with
> 20 hits and no errors or state mismatches; `cfr_streets: []` never touches the table.
