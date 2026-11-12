# B1 DIAG: final vs strong/s1_ranges (30 pairs x 200 hands, 12000 hands, 0 forfeits, full seeds)

**Headline: final wins +3.378 ± 0.094 chips/hand, match score 1.000 (30/30 pairs won).** Final is clearly winning; the
leaks below are upside, not damage control. Button +4.44/hand, big blind +2.32/hand.

## Opponent profile (from logs)
- Postflop it never bets: first-in bet rate 0.00 on flop/turn/river (n=6604/3601/2259) and it only checks.
- It folds 100% to every postflop bet of ours (flop n=2903, turn 1552, river 946), zero calls and zero raises.
- Preflop it is the only active one: opens/raises 63% first-in, raises 27% facing our raise, calls 39%.
  Its raise size is 5 (or 8 on a re-raise) in 99% of cases.
- All 2020 showdowns are check-check-check lines. It never wins a pot by betting, only by our folds and showdowns.

## Chip sinks by ending (all hands, +40534 total)
| ending | n | chips |
|---|---|---|
| WE fold preflop | 2560 | -8017 (avg -3.1) |
| showdown loss | 1063 | -7174 (avg -6.7) |
| showdown win | 892 | +7134 |
| OPP folds flop/turn/river/preflop | 2903/1552/946/2019 | +28078/+10282/+5425/+4806 |

Preflop-fold detail: we fold as SB after our own raise to a 3-bet n=496 (-2976, -6.0 each); BB fold to its raise to 5 n=1323 (-2646);
SB limp then fold to its raise n=624 (-1248); 2-bet re-raise folds n=44 (-975).

## Leak candidates
1. **Checking back weak hands that lose at showdown against a never-calls opponent.** n=1063 showdown losses, -7174 chips (a bet that
   folds it out flips each to about +6.7, so up to +14k = +1.2 chips/hand; real gain lower, we would not bluff every one).
   We bet only 39% of flops (2903/7412), 34% of turns, 32% of rivers; the other 2020 hands go check-check-check to a showdown that is
   ~even (+7134 vs -7174). Mechanism: we check hands that cannot win a showdown while it folds to any bet. Specific to this trait but
   the trait (postflop fold rate ~1.0 over n>=30 bets, no bets of its own) is observable. Move: when the opponent's postflop fold-to-bet
   rate is SPRT-high, bet (cheap size) every flop/turn/river where we would check back, instead of showing down.
   **Ivey: PRINCIPLE.** "If a guy never calls, you bet every street with nothing, you don't hope to win at showdown. The only way he
   fights back is by starting to call or raise, and then you see it in two hands and stop; keep the sizes small and the downside
   is a couple of blinds."
2. **Folding preflop to raises when the opponent surrenders every postflop pot.** n=2560, -8017. Almost all of it is 3-bet folds
   (496 x -6.0), BB folds to a 5-raise (1323 x -2.0), limp-folds (624 x -2.0). A call costs 3 more and gives the whole pot postflop by
   one bet, since it folds ~100%; pot odds are ~3 to 1 for any two cards. Mechanism: our preflop defence is calibrated to a balanced
   opponent, where weak hands lack equity; here equity realization is ~100% via fold equity. Move: with fold-to-bet trait on, defend
   (call) wider vs raises and 3-bets, then continue bets (needs #1 on, otherwise calling is wrong).
   Gain estimate not reliable (+0.3 to +0.8/hand); depends on #1. **Ivey: SITUATIONAL (only behind the postflop trait gate)** -
   "Against a normal player I fold trash to a raise. Against someone who cannot fight for a pot after the flop, I call every time, because
   I'm buying the flop cheaply and taking it down. If he starts barreling, the gate closes and I go back to folding."
3. **Over-sizing river bets against a folder (cost-free here).** river bet avg 37 vs flop 9.5, turn 8.8; since it never calls, extra
   size costs nothing now but a size-agnostic folder that starts calling would punish it. n=946, 0 chips lost now. Move: against a folder,
   bet the minimum that gets folds (half pot), not 37. **Ivey: PRINCIPLE** (small, but it is a free-roll insurance), expected gain ~0.
   Listed for completeness; do not ship alone.

No other real leak: seat split and size splits show nothing (82 pots >= 40, +4741, all wins).

## Caveats (honest)
- The opponent's 100% fold rate is observed on the 39% of flops where we chose to bet (selection: likely stronger hands plus some
  bluffs); behaviour of it against bets with our weakest hands is not directly measured, only the absence of any call/raise in
  5401 bets and of any bet of its own in ~12.5k postflop first-in spots. Leak 1 estimate is an upper bound.
- Leaks 1 and 2 are the same trait ("postflop folds to anything"): count as one leak seen once; need other batch-1 diag reports to
  reach the >= 2 bots bar. This session ran no experiments (diag only).
