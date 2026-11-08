# PA: gate X and `tier4p` with forced members (Opus, cloud)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/TIER4_PLAN.md` §P (P0a, P1 only), and on
`tier4/base`: `bot/brains/exploit.py`, `bot/brains/tier3x.py`, `docs/reports/TRACK_X.md` (X2/X3 sections).
Branch `tier4/p` from `origin/tier4/base`. Files: the P row of the README's ownership table.

## Tasks

1. **Gate X baseline (start it first, it runs while you code).** `tier3x` vs `tier3` on the training pool, 50 pairs,
   seeds 8000+, both locks on (score) and off (chips), the two arms back to back. Two-part KEEP
   (README rule 5). Record the numbers in `docs/reports/TIER4P.md`. This decides the **incumbent**: `tier3x` if KEEP,
   else `tier3`. `--processes` per README rule 3.
   Gate X only picks the development base (the incumbent); only I1's bar decides what ships.
2. **`bot/brains/tier4p.py`:** `Tier4PBrain(Tier3Brain)` with members as parameter overrides applied after
   `adjusted()` (same mechanism as `exploit.adjust`, a pure function over the params dict):
   - `base`: Tier 3 unchanged.
   - `anti_folder`: X3's over-folder move at λ = 1, plus X3's value-only move **only when the posterior's implied
     river bluff share is ≤ `x_vo_cut`** (0.10) — true for exploiter and rules, false for conv_opp3 (0.23 in
     `data/discard_holdem/types.json`).
   - `anti_value`: X3's value-only move; plus "fold medium hands to a trapper's raises" (new parameter).
   - `anti_aggro`: call down wider, fewer bluffs (new parameters; start small).
   Every member's numbers live in one dict per member (`MEMBERS` in `tier4p.py`), so PB can tune them through
   `tier4p:{json}` without code changes.
   A param `member` (default `"auto"`) **forces** one member when set (`tier4p:{"member":"anti_folder"}`). In `"auto"`
   mode, the hook `choose_member(...)` calls `bot/brains/tier4p_select.py`. Create that file as a stub that returns
   `"base"` (PC fills it in, and doesn't edit `tier4p.py`).
   `stats` counts hands per member (for `--report stats`).
   Any error in a member → Tier 3's params for that decision.
3. Register `tier4p` in `bot/main.py` (registry line only, not the default) and add it to `LOCK_BRAINS` in `lab/eval.py`.
4. **Tests** `tests/test_tier4p.py`: `member: "base"` plays exactly like `tier3` (same seed, same actions); each forced
   member changes only its own params; an exception in a member falls back to Tier 3's params; registry and
   `LOCK_BRAINS` entries exist.
5. Quick sanity: each forced member vs its family's training bots, 8 pairs, locks off, to catch a member that
   breaks play (not a gate).
6. Fast suite green, `-m slow tests/test_timing_slow.py` green, push, handoff.

## Done when
- Gate X verdict and numbers are in `docs/reports/TIER4P.md` and the handoff (incumbent named).
- `tier4p` exists with 4 forced members and the `choose_member` hook; tests pass.
- `docs/tier4/handoff/PA.md` lists the member parameter names and ranges that PB should tune (≤ 3 per member).
