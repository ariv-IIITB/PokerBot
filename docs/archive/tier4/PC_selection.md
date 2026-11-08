# PC: selection, bail-out, stop-loss, adversary bot (Opus, cloud)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/TIER4_PLAN.md` §P2, `docs/tier4/handoff/PA.md`, and on
the branch `bot/strategy/traits.py` (X1) and `bot/strategy/types.py` (X2).
Branch `tier4/p-sel` from `origin/tier4/p` (after PA). Selection, bail-out and stop-loss go in
`bot/brains/tier4p_select.py` (PA created it as a stub; PA's `choose_member` hook calls it). **Don't edit
`tier4p.py`**: PB tunes its values at the same time. Also `lab/sparring/adversary.py`, `tests/test_tier4p_select.py`.

## Tasks
1. **Selection** in `tier4p_select.py` (called once per hand through `choose_member`):
   - F = the X2 family with the highest posterior mass (summed over its types). Families → members:
     over-folder → `anti_folder`; value-only and trapper → `anti_value`; aggressor → `anti_aggro`;
     unknown, nit, station → `base`.
   - Play F's member only when mass(F) ≥ 0.8 for the last 20 of our decisions **and**: for `anti_folder`, X1's
     over-folder SPRT says yes; for `anti_value` and `anti_aggro`, ≥ 60 opponent decisions seen. Else `base`.
2. **Bail-out:** an X1 over-folder CUSUM alarm → `base`, and that member is blocked for 50 hands.
3. **Stop-loss:** if our net chips over the hands since the current member switched on are below 0 by more than 2 SE
   (per-hand SD measured in this match), play returns to `base` for the rest of the match. Checked only at 25/50/75 %
   of `total_hands`.
4. The endgame lock stays before everything (as in Tier 3). Locked hands don't count toward the stop-loss.
5. **Adversary bot** `lab/sparring/adversary.py`, registered like the other sparring bots: over-folds (folds to any
   postflop bet without a pair or better) for the first 100 hands, then calls everything down.
6. **Tests:** selection picks each member from a synthetic posterior/trait state, and `base` when either condition is
   missing; the CUSUM block lasts 50 hands; the stop-loss fires only at checkpoints, and only on a 2-SE loss; the
   adversary switches at hand 100; any error in selection → `base`.
7. Smoke runs (not gates): `tier4p` vs exploiter and vs the adversary, 8 pairs each, with `--report stats`, to check
   that members switch on and off as designed.
8. Fast suite green, `-m slow tests/test_timing_slow.py` green, push, handoff.

## Done when
- `docs/tier4/handoff/PC.md`: the rules as built, test list, smoke-run member shares, the commit.
