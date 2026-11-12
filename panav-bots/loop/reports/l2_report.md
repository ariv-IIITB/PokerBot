# Track L2: defence vs a frequent large bettor (12 Nov 2026). Verdict: FAIL (no passing change)

Branch `loop/L2`. Tools: `tools/l2_folds.py` (decision-level fold/call equity from logs), `tools/l2_duel.py` (file_duel + stderr capture),
`tools/l2_paired.py`, `tools/l2_suite.sh`, adversary `adversaries/switcher.py`, candidate `candidates/l2_defend.py` (REJECTED, not for shipping).
Base: final on lakshya1, seeds 1-9, 500-hand legs: -0.954 +-0.340 c/h (`results/l2_base_lakshya1.json`).

## Decision-level findings (seeds 1-9 logs, 4840 folds facing a bet; 700 sampled, equity MC vs top-p slice of its range, p = its bet rate)
- lakshya1 bets 75% flop / 58% turn / 36% river, 78% of flop bets >= 0.9 pot. Folds to our bets 41/51/72%.
- (a) Flop folds (2682 = 55% of fold decisions): only 28% have equity >= pot odds vs its top-70% range; 9% clear it by >= 0.15.
  Most flop folds (60%) are clear (margin < -0.05). Turn: 46% >= odds vs top-50% slice; river 50% vs top-35%.
- Calibration on our own CALLS: the slice model is right on the flop (realised continuation value +7.5 vs predicted +7.2) but overstates turn
  (+10.9 vs +36.9) and river (+9.8 vs +63): its big late bets are stronger than a top-p slice, plus reverse implied odds. So "equity >= odds" is not enough.
- (b) fold->raise: its response to our raises over a bet: fold 27% flop / 20% turn / 31% river, call ~52%, re-raise 21% flop. A raise of about 2x its
  1.5-pot bet needs ~55% folds to break even as a bluff. Not supported. (Our existing value raises over bets are very +EV: +13 flop, +58 turn, +30 river
  per raise, n=238/103/91, which is value, not bluff.)
- (d) preflop: it opens only 28% of button hands (limps 72%); BB folds 42% of its opens (11.7% of BB hands), we fold 53% of the time to its 3-bets (5% of opens).
  No wide-opener trait, tiny chips. Not pursued.
- (c) defend-only-the-best-slice, tried in-game (move `defend`): trait `bettor` (SPRT, p0 .45 / p1 .65 on flop+turn first-in bet rate), equity from
  our actual cards vs top-p slice (p = its measured street bet rate, clipped .40-.75), fold mass -> call when equity - price >= margin; kill switch if
  fired-hand value + 1.64 SE <= 0. Ledger = chips from the decision to hand end (net + chips already in; folding = 0).
  - margin .15, flop+turn, seeds 1-9: 395 fired, value -0.6/fired hand (zero), paired delta -0.10 +-0.39.
  - margin .05 diagnostic, same seeds, value by bin: flop margin < .2 about 0 or negative; flop >= .3 positive but n < 20; turn margin >= .2 +22..+35 per
    hand (n=53). Picked turn only, margin .20 (post hoc on those seeds).
  - Fresh seeds 31-39 (500 hands): base +0.20, cand +0.15, paired -0.05 +-0.45; ledger 145 fired, +17.9/fired hand (+2600 chips), showdown win 73%.
    The mechanism works against lakshya1-style bettors, but match noise (+-0.45) hides an effect of about +0.29 c/h.

## Suite (seeds 100-111, 12 pairs, 200-hand legs; paired delta cand-base c/h; fired = fired hands, value = ledger per fired hand)
| bot | delta +-SE | fired | value/fired |
|---|---|---|---|
| eqtag | -0.18 +-0.36 | 26 | -3.8 |
| s2_rollout | -0.36 +-0.56 | 98 | +0.9 |
| s3_exploit | +0.17 +-0.30 | 21 | -5.6 |
| new_lag | +0.90 +-0.91 | 220 | +3.6 |
| trapper | -0.04 +-0.37 | 11 | -26 |
| s1_ranges | -0.43 +-0.14 | 0 | - |
| new_trapper | -1.14 +-0.46 | 0 | - |
| new_eqrandom / new_rules / new_minraise | -0.04 / +0.00 / +0.22 (+-0.2-0.3) | 0 | - |
| conv_opp3 | -0.64 +-0.40 | 16 | -22.7 |
| potctl | +0.24 +-0.29 | 34 | -4.3 |
| polar | +0.67 +-0.77 | 0 | - |
| s4_balanced / s5_preflop / s6_discard | +0.10 / -0.28 / +0.31 (+-0.33-0.40) | 30 / 30 / 28 | -20 / -34 / -29 |
| switcher (wide 100 hands, then tight-value) | -0.46 +-0.95 | 106 | +26.5 |
Pooled over 17 bots: -0.057 +-0.119 c/h. Zero-fired bots swing by -1.1..+0.7 with identical play: that is run-to-run noise (solver is wall-clock driven).
Forfeits/illegal replies 0. Hook cost 0.19 ms per decision on average, 16 of 1666 calls over 5 ms (MC about 5-15 ms); bank use 40% vs 42% base.

## Ivey test
"Against someone who bets 75% of flops, its bets are mostly not value, so I call down my best hands at the odds. But I do it where my read is good: the
turn, and only when I am well clear of the price. It must not turn on against a balanced player, and must stop if the opponent tightens." Verdict:
SITUATIONAL. The principle (equity vs observed range beats price) is sound, but the `bettor` gate is too loose: it fired on balanced bots
(s3, s4, s5, s6, conv_opp3, trapper, potctl, eqtag) where the fired decisions lost (about -17 chips per fired hand pooled, n about 200).
## Why it fails
- Guard set fails: the mechanism loses where the trait is a false positive; the base 'equity >= odds' read is wrong against balanced ranges.
- Gain on lakshya1 is at most about +0.3 c/h, below the noise of 9 pairs; margin and turn-only were chosen on seeds 1-9.
- Switcher: no clear harm (-0.46 +-0.95) but also no gain; kill switch did not fire.
CONFIRM seeds 10-27 and the final holdout were NOT run: the candidate failed the guard set first.
## Next (not done)
A tighter gate (bet rate >= 0.70 AND big-bet share >= 0.6, i.e. lakshya1-like only) would likely remove the false positives, but that is nearly a one-bot
fit; the lakshya1 loss is a bet-first problem (Track L1), not a fold-too-much problem. Defence EV is mostly right as is.
