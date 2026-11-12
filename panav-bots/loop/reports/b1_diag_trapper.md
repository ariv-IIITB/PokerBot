# B1 DIAG: final vs spar/trapper

**Result (30 pairs x 200 hands, 12000 logged hands, 0 forfeits):** final +0.10 +- 0.35 chips/hand, match score 0.517.
That is indistinguishable from zero (SE 0.35). Final is not losing and not clearly winning.

## Where the chips go (leak_report)
- Showdown WIN +58212 (n=1293) vs showdown LOSS -51099 (n=880): net +7113 at showdown.
- We fold: preflop -5285 (n=2164), flop -9117 (n=1300), turn -13170 (n=739), river -10863 (n=446) = -38435 total.
- Opp folds: preflop +6973, flop +1723, turn +10181, river +13678 = +32555.
- Seats: button -0.07, big blind +0.28 chips/hand (balanced within noise).
- Trapper's trait: first-in bet 0.65 preflop / 0.61 flop / 0.40 turn / 0.27 river; folds to our river bet 0.68, turn 0.50, flop only 0.15.
- Our fold rate facing its raise: preflop 0.37 (n=5730), flop 0.36 (n=3570), turn 0.43 (n=1728), river 0.55 (n=804).
- Showdowns where it raised and we only called (n=519): we net +1319 and win 63%. Showdowns where both raised (n=1349): +5101, win 53%. Checked-down (n=111): +98.

## Verdict: no real leak
Every showdown line is net positive for us, so we are not over-calling its bets (calling it down wins 63%). Our folds are the mirror of its aggression and its folds are about equal in chips (-38.4k vs +32.6k plus showdown +7.1k). The folds cannot be scored as mistakes from the logs: its hole cards are hidden when we fold, so "we folded the best hand" is unobservable. I could not find a decision class that loses chips AND has a better general alternative with n>=30 and a measurable gain.

## Leak candidates (weak, not recommended)
1. **River fold rate 0.55 vs a river first-in bet rate of only 0.27** (n=804, -10863 chips across all river folds, but that figure is the cost of folds we would have lost anyway).
   - Mechanism: it bets river rarely, so its river bets should be value-heavy; folding 55% looks about right. No evidence of over-folding; the 63% win rate when we do call suggests the calling range is fine.
   - General (trait: low river bet frequency => value-heavy). Move: none; do not loosen river calls.
   - Ivey verdict: SITUATIONAL. A great player folds more, not less, to a player who rarely bets the river; calling wider would be exploited by a passive-then-value player and past experience (12 Nov overbetdef) says marginal extra calls lose chips.
2. **Flop: opponent folds only 15% to our bets (n=2003)**, vs 50-68% on turn/river.
   - Mechanism: it defends flop wide and gives up later. Our flop continuation bets as bluffs earn little; turn/river barrels earn +10.2k/+13.7k.
   - General (trait: low flop fold-to-bet, high turn/river fold). Move: bluff less on the flop, keep barreling later, behind the fold-to-bet SPRT trait.
   - Ivey verdict: SITUATIONAL. Right against a station-like flop defender, but it is a trait that flips (a player who calls flop and folds turn is exploited by double barrels); only a hypothesis, I did not measure our flop bluff share or chips, so I do not rate it above noise.

Not run: per-bet-size and per-hand-class breakdowns beyond the above; the SE of 0.35 means any leak under about 1 chip/hand is undetectable at 30 pairs.
