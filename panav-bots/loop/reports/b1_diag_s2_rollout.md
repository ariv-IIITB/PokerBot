# B1 DIAG: final vs strong/s2_rollout (30 pairs x 200 hands, 12000 hands, 0 forfeits)

**Headline: final wins, +0.965 +- 0.35 chips/hand (about 2.8 SE), match score 0.650 (30 pairs). Seats: button +0.53, BB +1.40/hand.**
Run took 3 min (not the 25 min cap), so the full 30 pairs were used.

## Chip sinks by ending (A's chips; "sink" is mostly the normal cost of folding / losing)
| ending | n | chips |
|---|---|---|
| showdown LOSS | 464 | -45458 (vs showdown WIN 1083, +80856: net +35.4k) |
| WE fold @turn | 933 | -19124 |
| WE fold @flop | 2288 | -18380 |
| WE fold @river | 362 | -11971 |
| WE fold @preflop | 2122 | -5040 |
Gains: OPP folds @river 433 +12500, @preflop 3263 +6892, @turn 449 +6518, @flop 528 +4787.
Opponent: opens/bets a lot (preflop first-in bet 0.65, flop 0.80, turn 0.67, river 0.38); folds 0.75 to our river bets, 0.48 to turn bets, 0.33 to flop bets, raises our flop bets 0.33.

Overall: final is simply winning. No big, clear leak. The chip-loss rows above are the unavoidable side of a +0.97 result (showdown wins outweigh losses 1.8:1).
Our called river bets: 140 W / 143 L, +1.1k net, so calls are about break-even (pot odds fine; no sign of a hero-call or over-fold problem there).
Opp river bets that reach showdown: 172 W (+20.3k) / 172 L (-17.5k): the opponent's river bets are not obviously bluff-heavy.

## Leak candidates (weak; selection bias in logs applies, see PLAYBOOK `overbetdef`)
1. **Over-folding to high-frequency flop/turn bets.** n = 2288 flop folds + 933 turn folds (-37.5k chips of folded investment). Mechanism: opp bets flop 80% / turn 67% first-in, so its bet range is wide, while we fold ~2.3k flops. Folds after we already put chips in on the street: flop 1053 (-10.4k), turn 300 (-7.1k); folding to a re-raise after our raise/bet: flop 222 (-5.5k), turn 64 (-2.4k). General (trait: opp bet frequency >> value density). Move: when the opponent's within-leg bet freq is high, defend wider vs small bets (call/raise more). The logs cannot show the EV of the unplayed calls, so this is unproven; a fold's chips are not the cost of the leak.
   Ivey: SITUATIONAL. Vs someone who fires every street you defend more and let them bluff into you, but only after they show it, since a tight opponent who adds value punishes it; gate on SPRT bet-frequency and cap the extra defense to the cheaper bet sizes. This is exactly the call-more move that lost 0.69/hand on 12 Nov, so run it only behind the trait and check by mechanism.
2. **Bet river more vs a high river-fold opponent.** n = 579 river bets faced, opp folds 0.75 (433 folds, +12.5k, +29 chips each). It bets river only 38% first-in. Mechanism: opp folds at the river far more than a balanced fold rate (about 0.33-0.5 vs a normal-size bet); we bet river only about 20% of river nodes (estimated). General (trait: fold-to-river-bet high). Move: add thin value + extra bluffs on the river once the SPRT shows fold-to-river-bet above about 0.6.
   Ivey: PRINCIPLE. A great player bets more when the opponent folds too much to the last bet, and checks back to showdown when they stop folding. It can be exploited back only if the opponent starts calling; the SPRT gate turns it off again. Check it with the mechanism log: bluff success rate per added bet.
3. **Preflop folds as the SB/button vs wide opener** (n = 2122 preflop folds, -5.0k; 1660 of them to the first raise, -3.3k, mostly blind money). Opp opens 65% preflop and folds 0.39 to our raises. Mechanism: we likely already 3-bet or call enough (BB seat is +1.40/hand); only a minor upside. SPECIFIC to this opponent's range width, small chips.
   Ivey: SITUATIONAL (low value; 3-bet more light vs a wide opener behind the trait gate). Not worth a move on its own.

## Not a leak
- Showdown losses (-45.5k) are the normal other side of showdown wins. River bluff-catching is about break-even, so no change recommended.

## Recommendation
Not enough evidence for edits from this bot alone. Pass #2 (river fold-to-bet exploit) and #1 (defend vs wide bettor) to INTEGRATE only if other batch-1 bots show the same patterns (>= 2 bots rule). Fold chips are not a leak by themselves.
