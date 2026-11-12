# Track L: beat aggressive bettors (lakshya1-style) without overfitting (12 Nov 2026, owner's priority)

Read PLAYBOOK.md first (tools, bundle_tool, Ivey test, overfit rules), then `panav-bots/src_changes/lakshya1_analysis_12nov.md`
(why final loses to `panav-bots/opponents/lakshya1.py`: it bets 70% of flops / 53% turn / 37% river at 1.2-1.4x pot, final bets 33-38% at ~0.6x and
raises only 5% of the time it faces a bet, folds 50% of all hands vs 33%; showdowns are even; lakshya1 folds 43% flop / 54% turn / 73% river to OUR bets).
Final lost -0.64 chips/hand over 1000 hands (5 of 18 matches won); at 400 hands it is level. `overbetdef` (fold->call vs overbets) made it WORSE (-0.69): do not repeat it.

## Goal
A final-derived bot that beats lakshya1 over Stage 2 length (`--hands 500` per leg = 1000 hands per match, paired deals), AND is not worse on other bots.
Success is judged on seeds you never tuned on. A candidate that only beats lakshya1 = overfit = rejected. No change that you cannot explain as a poker principle
a great heads-up player would use against ANY opponent with the same observed behaviour.

## Sets and seeds (strict)
- Target: lakshya1. DEV seeds 1-9 (use for design and tuning). CONFIRM seeds 10-27: run ONCE per final candidate, only at the end. Report both.
- Aggressive-bettor generalisation set (dev, seeds 100-115, 200-hand legs): strong/s2_rollout, strong/s3_exploit, spar/eqtag, Opps/discard/new_lag.
- Guard set (candidate must not be worse; seeds 100-115): spar/trapper, strong/s1_ranges, Opps/discard/{new_trapper,new_eqrandom,new_rules,new_minraise,conv_opp3}, spar/potctl, spar/polar,
  strong/s4_balanced, strong/s5_preflop, strong/s6_discard (path `panav-bots/eval_bots/{spar,strong}/<name>/bot.py`).
- Final holdout, never opened until the very end (run once, black-box): spar/{betfold,light3b,donk,adapt,tilt,discardread}, strong/{s7_solver,s8_meta,s9_sizing,s10_regret}.
- Base numbers are paired: run base final on exactly the same seeds first, save to `panav-bots/loop/results/<your-prefix>_base_<bot>.json`.

## Rules of the road
- Gates on OBSERVED behaviour within the leg only (never the opponent's name or card patterns): e.g. opponent first-in bet rate, share of bets >= pot, fold rate to our bets by street,
  fold rate to our raises. Thresholds must come from a principle, e.g. a bet of size s (pot fractions) breaks even as a bluff at fold rate s/(1+s); MDF = 1/(1+s).
  A move must be bounded (cap on the probability mass it moves), ramp in with evidence, and switch OFF when the trait weakens (use windows, see existing SPRT/ramp code).
- Mechanism proof for each move: counters of how often it fired and the realised result of exactly those decisions (chips won/lost in hands where it changed the action vs the
  average of the base policy there is not directly observable, so log: fired, then fold-rate achieved for bluffs, showdown win rate for thin value/raise-calls, net chips of hands containing a fired decision).
- Exploit-back test: the move must not lose to an opponent that switches style. Include `spar/adapt`-style and `Opps/discard/new_exploiter` ONLY if you did not put them in a held-out set above; otherwise
  write a tiny scripted opponent (stdlib bot that bets wide for 100 hands then plays tight-value) in `panav-bots/loop/adversaries/` and test cand vs that and vs base.
- Time/legality: mean reply <= 20 ms, worst <= 80 ms, no forfeits, zero illegal replies, no stdout noise. Patch only exploit/policy glue; never the blob.
- Matches: <= 3 processes, use `timeout`, run long jobs in the background and poll. 1000-hand matches are long: measure first how long one takes, then size the plan.
- Push partial work early and often to your branch (every ~45 min): reports, results JSON, candidate bot, patched sources. Never push elsewhere.
- Final report `panav-bots/loop/reports/<prefix>_report.md` (<= 90 lines): moves, Ivey verdicts, mechanism counters, table of paired deltas (cand-base, +-SE) for lakshya1 dev, lakshya1 confirm,
  aggressive set, guard set, final holdout, head-to-head cand vs base; verdict PASS / FAIL / PARTIAL. Honest outcome 'no passing change' is acceptable. Wall-clock cap 4 hours.
