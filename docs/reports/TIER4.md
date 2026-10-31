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
