# ADT: exploit-layer adaptation speed at 200-hand legs

Branch `claude/adt-ac9719` (push target `tier4/adt`) on `tier4/int` HEAD `4b3dbc3`. **NO-GO on every
candidate tested** — reverted, nothing merged. 14-core laptop, shared with other sub-plans concurrently.

## Diagnosis (hand number traces, 20 legs/bot, seeds 82000-82019, 200h/30s legs, defaults)
Over-folder SPRT verdict / lambda ramp, and value-only (X2) lambda ramp, read every hand:
- **d_new_exploiter**: SPRT decides fast (median hand 36, 18/20 legs) but **25% of legs never finish
  the ramp** within 200 hands (full ramp median hand 84, range 54-140); X2 ramps fast (median 20).
  Bottleneck: partial ramp, not verdict speed — `x_ramp` *should* help here.
- **d_conv_opp3**: SPRT **never reaches a verdict in 60% of legs** (8/20 decide, median hand 90, range
  22-146). Bottleneck is verdict speed itself — `x_ramp` cannot help the 60% that never decide.
- **d_new_trapper**: over-folder SPRT **never decides in 20/20 legs** (not an over-folder; expected) and
  X2 already ramps fast (median hand 18). Neither lever applies — its score drop (.912->.800 in the
  manager's 40-pair final check) is **not explained by X1/X2 timing** at all.
- **d_new_lag**, **d_new_rules** (controls): lag never triggers X1 either (consistent with flat score);
  rules' SPRT decides ~58% of legs, similar profile to the others.

## Tried (coordinate descent, train pool = 6 bots, locks-off chips, hands=200/bank=30, seeds 82100+)
1. **x_ramp** 20(base)->8/12: n=30 looked promising (sum +1.35/+1.34 ± 1.1, driven by d_new_minraise,
   not a target bot); **at n=60 (sequential-test rule) it washed to noise**: sum +0.24 ± 0.80 (z +0.3),
   target bots individually <1 SE (exploiter -0.05, conv_opp3 +0.15, trapper -0.15). x_ramp=5 was
   worse than baseline (sum -0.65) — too fast a ramp overreacts. **NO-GO.**
2. **x_vo_min_obs** 60->25/40 (n=30): sum +0.40/+0.53 ± ~1.1, trending *slightly negative* for the two
   target bots that use X2 most (exploiter -0.27/-0.24, conv_opp3 -0.08/-0.14); only non-target bots
   (minraise, rules) moved. Consistent with the diagnosis: X2 was already fast, so lowering its gate
   has nothing to fix and only risks firing on noisier evidence. **NO-GO, didn't extend to n=60.**
3. **ALPHA=BETA** 0.05->0.10 in `traits.py` (shared by all 3 traits + both X1/X2; the "bigger lever" for
   conv_opp3's verdict-speed bottleneck) — tested broadly (full train pool, n=60, not just the 3 targets,
   per the brief's own caution): conv_opp3's verdict rate improved only to 10/20 legs (median hand 46,
   still half never decide) and chips moved +0.27 ± 0.26 (z 1.0, not significant); sum over the pool
   +0.09 ± 0.78 (z 0.1) — flat. `d_new_lag`/`d_new_rules` (must-not-regress) trended slightly *negative*
   (-0.32, -0.20; neither >1 SE). Side effect found: relaxing ALPHA/BETA changes our play early enough
   to alter the actual hands reached, which *reduced* conv_opp3's X2 convergence in the same run (0/20
   legs reached value-only >=0.5, vs 4/20 at the default) — a live feedback loop, not a bug. **NO-GO**;
   reverted (`git checkout -- bot/strategy/traits.py`, confirmed back to 0.05, tree clean).

Three distinct levers tried, none moved the needle beyond noise at a fair sample size — stopping per
the three-strikes rule rather than trying further variations blind.

## Not reached
HANDOFF_NEXT idea (a) preflop-stat feeding and (b) embedded priors from `logs/records/s0_9000` — bigger
changes, unmeasured. Given (1) conv_opp3's real bottleneck is 200 hands just not being enough evidence
for its true rate near the SPRT boundary (not fixable by nudging thresholds without hurting error rates
pool-wide) and (2) trapper's degradation isn't an X1/X2 timing problem at all, **(b) priors from
recordings is the more promising next lever for conv_opp3** (it changes what's known at hand 0, not how
fast it's learned); trapper needs a different diagnosis first (check `x_narrow`/`x_def` convergence,
or whether .912->.800 is itself within the original 40-pair run's noise — no SE was reported for it).

No timing check run (no code change ships) and no confirmation run (nothing to confirm). Fast suite
green on this branch (unmodified `tier4/int`). Commit: none beyond this handoff (tree otherwise clean
at `4b3dbc3`). Pushed as `claude/adt-ac9719` / `tier4/adt`.
