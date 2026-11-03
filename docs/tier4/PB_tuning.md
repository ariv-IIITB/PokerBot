# PB: tune the members (Sonnet, cloud, mostly compute)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/tier4/handoff/PA.md`.
Branch `tier4/p-tune` from `origin/tier4/p` (after PA). Edit only the `MEMBERS` values in `bot/brains/tier4p.py`
and `docs/reports/TIER4P.md` (PC edits other parts of `tier4p.py` at the same time: keep your diff to the values).

## Tasks
For each member `anti_folder`, `anti_value`, `anti_aggro` (members forced with `tier4p:{"member":...}`):

1. **Grid:** the ≤ 3 parameters × 3 values from PA's handoff (≤ 27 points). 16 pairs per point, locks off,
   `--processes` = nproc − 1 (cloud), seeds 10000+ (new block per member), against the member's family:
   - `anti_folder`: exploiter, conv_opp3, rules
   - `anti_value`: minraise, trapper
   - `anti_aggro`: lag, maniac
   Script the grid (a small shell loop over `lab.eval tier4p:{json} --pool ...`); one point at a time.
2. **Confirm** the best 2 points on fresh seeds (11000+): 50 pairs vs the family, locks off and on.
3. **Restriction:** each confirmed point vs Tier 3 head-to-head, 50 pairs: not worse than −0.10 chips/hand and match
   score ≥ 0.5 − 2 SE. A point that fails is rejected even if it wins against its family.
4. Set the winning values in `MEMBERS`. If no point beats the member's starting values by > 2 SE against its family,
   keep the starting values and say so.
5. Fast suite green, push, handoff.

**Cloud results only rank grid points.** The binding KEEP for each chosen point is PD's step 0 on the laptop.
Compute guide: `anti_folder` ≈ 1.3 M hands (exploiter, the slowest bot, plays ~96 hands/s on the whole laptop), the
others ≈ 0.4 M each. Run `anti_folder` first: it is the largest.

## Done when
- Each member: grid table, the 2 confirmed points with ± SE, the restriction check, the chosen values — all in
  `docs/reports/TIER4P.md`.
- `docs/tier4/handoff/PB.md` with the final values and the commit.
