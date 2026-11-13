# EX1: league search vs final (13 Nov) — HONEST OUTCOME: no config beats final beyond noise

## What was run (scaled down; container was reclaimed once, parent asked for a <=90 min delivery)
- Bot family: `league/param_bot.py` (17 params: preflop open/defend/3bet/fold-to-3bet; bet freq flop/turn/river; probe; sizes per street 0.25-2.5;
  bluff share; check-raise; raise-when-bet-into; call margin; give-up; use of revealed discard). `league/make_bot.py PARAMS.json OUT.py` bakes a standalone file.
  7 corner styles in `league/configs/corners.json` (nit, station, maniac, overbettor, checkraiser, probebettor, default).
- Search (`league/search.py`): r0 = 7 corners + 7 uniform random, then 2 cross-entropy rounds (pop 12, top-2 re-tested on fresh deals), 8 pairs x 200 h per config,
  seeds 1000-1023, opponent `loop/evalbuilds/final_seeded.py` (pinned solver). 38 evaluations total (planned 124; cut for time).
- Confirmation: the 4 selected configs vs the normal `final/bot.py`, seeds 2000-2023 (24 pairs x 200 h) and 2050-2057 (8 pairs x 500 h). Seeds ledger: `results/SEEDS.md`. 3000+ untouched.

## Search result: nothing wins
- r0: best -0.04 (default-like config), median -0.96; maniac -7.7 (loses badly), nit -1.9, station -1.3.
- Best single evaluation: r1_09 +0.41 +- 0.48. Its fresh-deal re-test (r2_10): -1.53 +- 0.60. That is pure selection noise (winner's curse), not an exploit.
- The pooled top-3 by mean of repeated evaluations (W1-W3) and r1_09 (W4) went to confirmation.

## Confirmation (chips/hand of the param bot vs final, +- SE over duplicate pairs; negative = final wins)
| config | 24x200 (2000-2023) | 8x500 (2050-2057) | match score 24x200 |
|---|---|---|---|
| W1 (r1_07: open .58, big turn/flop bets 1.35-1.6x pot, bluff .54, giveup .56) | -0.59 +- 0.32 | -0.25 +- 0.35 | 0.354 |
| W2 (r0_00/r1_11 family: open .45, defend .5, sizes ~1x, bluff .69)            | -0.89 +- 0.29 | -0.10 +- 0.27 | 0.354 |
| W3 (r2_08: probe .48, size .58 all streets, raise_bi .47)                      | -0.88 +- 0.30 | -0.53 +- 0.71 | 0.292 |
| W4 (r1_09: raise_bi 1.0, small sizes, 3bet 0)                                  | -1.06 +- 0.37 | -1.07 +- 0.50 | 0.333 |
Config params: `league/configs/W1..W4.json`; bot files `league/W1..W4.py`. No forfeits, no illegal replies in any run.
=> **0 of 4 confirmed.** All are negative on 24 pairs; the shrinkage from the +0.41 winner (to -1.0) is noise. Base-vs-base noise is about +-0.4 at 16 pairs (parent note).

## Vulnerability clusters (candidates only; none is confirmed as an exploit)
Because no config wins, there is no cluster of winners to describe. What the logs of the best three (W1-W3, `leak_report`, 9,600 hands each) do show about where *final* gains and where it might be soft:
1. Final wins chips mostly at showdown (our bots lose +-40-52k in showdown losses vs ~+40-44k wins; net negative in BB seat: W1 -1.17, W2 -1.29, W3 -1.65, W4 -1.95 chips/hand, button about 0 to -0.5). The param family is weak out of position; final's edge is positional/solver based, not a leak to copy.
2. Final's own aggression: vs every config it bets first-in preflop 0.68-0.73 and folds to our bets 0.35 preflop. A config that 3-bets more (three .12, W1/W3) got no better result (-0.59/-0.88): the preflop fold rate is not exploitable at these sizes with this postflop skill.
3. Flop/turn fold-to-bet 0.37-0.67 depending on config (lowest 0.37 vs W3 = small probe bets called more); W3 had the lowest match score (0.29): small frequent bets did worst.
4. River: final folds to our bets 0.39-0.50 (W1 .39, W2 .49, W4 .50) while calling profile at flop is high (call .55 vs W3). Big river bets (W2, bet_r .32, ~.68 pot) did not yield profit; WE fold @river costs us -0.84 to -1.18/hand, i.e. our bluffs get called/shoved over.
5. Overbet/maniac style (corner "maniac", sizes ~1 pot, bet 1.0) lost -7.7: final does not fold to pressure.
These are observations about the bots' losses, not exploitable weaknesses of final; do NOT turn them into moves.

## Zoo check (W1 vs zoo bots, 8 pairs x 200, seeds 2060-2067; +- SE)
| opp | W1 chips/hand | score |
|---|---|---|
| spar/eqtag | -1.27 +- 0.30 | 0.31 |
| strong/s1_ranges | +0.30 +- 0.12 | 0.84 |
| Opps new_lag | +3.05 +- 0.76 | 0.75 |
| Opps conv_opp3 | -1.01 +- 0.47 | 0.38 |
| lakshya1 | -1.44 +- 0.97 | 0.25 |
W1 is a mediocre generic bot (beats weak/loose bots, loses to equity-based ones): it is neither specially strong nor specifically anti-final. Final vs W1 on the same seeds: +1.51 +- 0.63.

## Diagnostic: lakshya1 vs the param family (not tuned to it)
Final vs lakshya1 here: +0.19 +- 0.36 (8 pairs; no loss visible in this sample, unlike earlier reports). lakshya1's behaviour vs final (3,200 hands): preflop first-in bet 0.30,
calls our preflop raises 0.71 (folds 0.22); flop first-in bet 0.66, turn 0.48, river 0.35; folds to our river bets 0.73, flop 0.45, turn 0.53.
That is a loose-passive-preflop, high-c-bet postflop bettor: nearest param region = low `open` (<~0.45) + high `defend` + high `bet_f` / `probe` (closest tested: W3 probe .48, open .45;
W2 open .45, defend .5). Both lose to final here (-0.9). So lakshya1 is NOT near any config this search found to be good; it is not a point inside a proven weakness region.

## Caveats
- Search budget was ~30% of plan (38 evals, 8 pairs each, SE about 0.5): it cannot rule out a narrow winning region. It only says that random/CE sampling of this family
  found no positive config that survived fresh deals, and every confirmed estimate is negative.
- Param bots share one equity engine (BaseBot) and are far weaker postflop than final; a stronger family or a longer search (reserve seeds 3000+ untouched) is the next step if wanted.
- Opponent in the search was `final_seeded.py`, confirmation used `final/bot.py` (agree: all negative).
