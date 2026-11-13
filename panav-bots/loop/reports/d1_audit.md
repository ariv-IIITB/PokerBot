# D1 node-level audit of final_seeded (13 Nov 2026; no bot edits)
Data: `final_seeded` vs 7 bots, duplicate pairs, real protocol, 30 s bank/200h leg. 60 pairs x 200h each (seeds 6000-6059, 168,000 logged
hands) + 30 pairs x 500h vs lakshya1 and new_eqrandom (seeds 6100-6129). Logs are not committed (size); tools: `panav-bots/loop/tools/d1_*.py`,
full tables `reports/d1_tables_200h.txt`, `d1_tables_500h.txt`. Pipeline: `d1_nodes.py` (one row per decision: size, equity-vs-random, chips from
the decision on = net + chips already put in; fold = 0) -> `d1_discard.py` -> `d1_report.py`. Evaluator = the bot's own numpy best-5-of-7.
| bot | chips/hand ± SE | match score | | bot | chips/hand ± SE | score |
|---|---|---|---|---|---|---|
| lakshya1 | -0.31 ± 0.23 | .408 | | new_exploiter | +0.26 ± 0.13 | .558 |
| new_geometric | -0.18 ± 0.14 | .483 | | new_eqrandom | +0.40 ± 0.16 | .525 |
| conv_opp3 | -0.15 ± 0.13 | .471 | | new_minraise | -0.17 ± 0.14 | .500 |
| potctl | +0.18 ± 0.14 | .550 | | lakshya1 500h / eqrandom 500h | -0.36 ± 0.20 / -0.15 ± 0.19 | .383 / .442 |
Amounts verified: history `amount` = per-street cumulative "raise to"/"call to"; request `pot` includes the opponent's bet; replies recovered as
`final_history[len(request.history)]`. Size f = translate's definition (open: X/pot_before; raise: (X-our_bet)/(pot_before+their_to_call)).

## 1. Headline: calls of ~pot-size bets (0.75-1.2 pot) postflop are the leak (exact, not an estimate)
Facing a postflop bet of 0.75-1.2 pot, final calls with hands of equity-vs-random below .9 and loses **-15 to -40 chips per call vs folding**:
flop -18.2±2.3 (eq .65-.8, n=998), turn -34.1±3.5 (n=489), river -40.3±5.2 (n=143); no equity bucket below .9 breaks even, only eq>=.9 wins (+48).
Because a call->fold only truncates the hand, its value on these logs is exact: **folding every such call with eq<.9 would have gained +0.64 c/h
pooled (SE 0.04)**: per bot conv_opp3 +1.29, lakshya1 +0.31, eqrandom +0.51, exploiter +0.38, geometric +0.62, potctl +1.36, minraise 0 (never bets
that size). Seeds 6000-29: +0.57, seeds 6030-59: +0.71. Fresh seeds, 500h: lakshya1 +0.49±0.07, eqrandom +0.54±0.05. By street (eq<.9): flop +0.30,
turn +0.26, river +0.07; by seat: button +0.48, BB +0.16. Same test on other sizes: calls of 0.33-0.75 pot are profitable (fold would cost -0.44 c/h),
calls of 1.2-2.0 cost -0.24 c/h to fold, all-in calls with eq<.8 lose big (river -78) and final already folds them (67-95%). Limits: the opponent's
response to a changed folding frequency is not measured (static bots only); equity-vs-random is a proxy for hand class; 6/6 bots agree in sign.

## 2. Discard audit (24,500 discards, 3,500 per bot; MC 4000 samples/keep with common random numbers, exact enumeration vs the shown hand at showdown)
final discards in 0.44 of hands. Loss = best-keep equity - chosen-keep equity (vs a uniform random opponent hand, 46 unseen cards).
- Chosen keep is the equity-best one in 82%; **>=3 pts worse in 8.8%** (>=6 pts 6.3%); mean loss **1.27 pts = 0.28 chips per discard at the pot
  of the discard** (lower bound: bets follow) = ~0.12 c/h at today's pot, plausibly 0.25-0.3 c/h with later betting. Per bot 1.15-1.42 pts, no outlier.
  Vs the opponent's actual kept hand (showdown subset, n=10,321): 14.7% >=3 pts, 2.04 pts (selection: showdowns only).
- By chosen keep type (share >=3 pts / mean loss pts / chips per discard): made hands are right (2pair .007/.06, top_pair .005/.09, pocket_pair
  .018/.18, trips .005/.08, pair+draw 0). The loss sits in no-pair keeps: **high 38.9% / 6.4 / 1.24 (n=2592)**, suited_conn_hi 36% / 5.5 / 1.64,
  board_pair 19.9% / 2.3 / .48, overcards 14.6% / 1.9 / .55, high+sd 13% / 1.7 / .41. Top mistakes: high->high 544, board_pair->board_pair 285,
  keeps no pair although a pocket pair was available 166 (e.g. 2c4d4s on Qc6s9c keeps 2c4d: .16 vs .46 for 4d4s), high->pair_other 89.
- By seat: button 1.39 pts / 0.33 chips per discard, BB 1.13 pts / 0.23. 500h legs: identical (1.17 pts, 7.7% >=3).
- Caveat: the blueprint chooses by a bucket b3 and a mixed row (`decide_discard`), not by equity; part of the 6 pts may be the equilibrium's
  deception/range logic. Realised value needs a replay of the rest of the hand with the other keep.

## 3. Oversize bets (all in `reports/d1_tables_200h.txt`, per street x seat x size bucket: response mix, mean eq of fold/call/raise, chips)
Tree: open sizes flop .33/.75, turn/river .5/1.0, facing a bet only "pot raise" + all-in; sizes above the biggest non-all-in map between it and all-in.
Pooled postflop open bets, inside (<= tree max+.12) vs above:
| street | inside: fold/call/raise, call chips | above: fold/call/raise, call chips | all-in: fold, call chips |
|---|---|---|---|
| flop (max .75) | .33/.57/.10, +3.6±0.4 (n=28k) | .58/.39/.03, +0.6±0.9 (n=17k) | .78, -36 (n=29 calls) |
| turn (max 1.0) | .41/.50/.09, +8.4±0.7 | .58/.39/.02, +23.8±2.4 | .63, +59±15 |
| river (max 1.0) | .52/.36/.12, +12.6±0.9 | .65/.28/.07, +22.8±3.2 | .53, +70±8 |
- Above the tree final folds 17-25 pts more but its calls are break-even or better (flop +0.6, turn/river +23): no evidence of over-folding overbets;
  ladder (1.2-2 pot): calls with eq .35-.8 earn about 0 (-1.4..+2.7) on the flop, so folding them costs nothing, and calling them gains nothing.
  Unlike the pot-size bucket, overbets are not the leak. Raising over a bet is rare (2-12%) and pays well (+9..+58) except river raises (see 5).
- The pot-size (.75-1.2) bucket is where the tree tops out on turn/river and where `fold` (48-63%) is not high enough (section 1).

## 4. Position (button vs BB, chips/hand ± SE of one bot's 24,000 hands per seat, about 0.3)
Pooled mean of per-bot results: button -0.05 (sd across bots .28), BB +0.05 (.35): no systematic position leak. lakshya1: button -0.43, BB -0.19;
conv_opp3 -0.40/+0.09; geometric 0.00/-0.37; minraise -0.03/-0.32; eqrandom +0.30/+0.50; exploiter +0.19/+0.33; potctl +0.03/+0.32.
By ending (pooled chips/hand of the seat): button WE fold@turn -1.29, @river -1.18, @flop -0.78; BB -0.79/-0.77/-0.74; showdown +0.39 / +0.53.
Button folds more later streets and its pot-size calls lose 3x more than the BB's (section 1). Entering flop/turn/river is worth +5.6/+11.1/+19.7 (button),
+5.9/+11.1/+18.7 (BB). 500h legs: both lose in the last 100 hands (-0.97 and -0.59 vs +-0.4 SE); behaviour (fold/call mix, time bank 53 s of 75 left) is
unchanged and the loss is in showdown chips, so treat as noise/opponent drift until repeated.

## 5. Cells ranked by chips lost (street x seat x facing size x our eq bucket x action; pooled over the 7 bots, 200h)
Robust ranking = continuing facing a bet, loss = -sum(chips from the decision) (fold pays exactly 0). Table B compares with another action (hidden info
differs, confounded) and is only a hint. Seat b = button.
| # | cell (street, seat, size, eq, action) | n | mean±SE | loss | bots losing | SE(loss) |
|---|---|---|---|---|---|---|
| 1 | flop b .75-1.2 eq.65-.8 call | 998 | -18.2±2.3 | 18,190 | 6/7 | 2,306 |
| 2 | turn b .75-1.2 eq.65-.8 call | 489 | -34.1±3.5 | 16,666 | 6/7 | 1,696 |
| 3 | flop b .75-1.2 eq.5-.65 call | 717 | -12.3±2.5 | 8,839 | 6/7 | 1,819 |
| 4 | preflop b .75-1.2 eq.5-.65 call | 2,561 | -3.0±1.2 | 7,718 | 6/7 | 3,000 |
| 5 | flop BB .75-1.2 eq.65-.8 call | 535 | -11.3±2.9 | 6,044 | 5/7 | 1,555 |
| 6 | river b .75-1.2 eq.65-.8 call | 143 | -40.3±5.2 | 5,758 | 6/7 | 747 |
| 7 | turn BB .75-1.2 eq.65-.8 call | 250 | -21.3±5.1 | 5,320 | 6/7 | 1,280 |
| 8 | flop b .75-1.2 eq.35-.5 call | 309 | -12.3±3.3 | 3,810 | 5/7 | 1,028 |
| 9 | river b .33-.75 eq<.35 raise | 43 | -83.1±13.0 | 3,573 | 2/7 | 559 |
| 10 | turn b .33-.75 eq.5-.65 raise | 234 | -14.2±4.7 | 3,313 | 4/7 | 1,094 |
Eight of the ten are the pot-size call (section 1). The 500h legs add river raises over a .33-.75 bet with eq .5-.8 (n=102, about -100 each; 2/2 bots);
in the 200h pool river raises are on average +66 so it is a hand-class issue (bluff-raises with the wrong hands), not raising per se.

### Hypotheses for the counterfactual replay (top 3)
1. **Pot-size calls -> folds.** Replace call by fold when facing a postflop bet of .75-1.2 pot (not all-in) unless the hand is in the top ~10%
   (eq vs random >= .9, or a made hand better than top pair / nut draw). Predicted gain +0.4..0.6 c/h vs the 7 bots. Test with the opponent re-simulated
   (do they bluff more when we fold more? new_exploiter adapts), thresholds .8/.9/.95 and per street, plus button-only; check calls of .33-.75 stay unchanged.
2. **Value-extraction vs slow-play (confounded, needs the replay to be believed).** BB first to act on the flop checks 62% of eq .8-.9 hands
   (check +8.6±0.9 n=3700 vs bet +21.1±1.4 n=2305), eq>=.95 check +20.9 vs bet +43.1 (flop); facing small bets with eq>=.8 final calls (turn b .33-.75:
   +31 n=1829) where its raises earn +85 (n=499). Test: override check->bet (1/3-3/4 pot) and call->raise for eq>=.8 hands; the replay must model the
   opponent's fold/raise response to the changed line (the logs only show the actions taken).
3. **Discard: pick the equity-max keep when it is >=3 pts better** (8.8% of discards, mostly no-pair hands, 0.12-0.3 c/h). The replay must play the rest of
   the hand with the new keep (final's own continuation) because air hands that keep a better draw also change bluff/fold behaviour; also test only
   overriding when the equity-best keep is a pair/draw and the chosen one is not (the 166 + 89 cases above).
Not found: over-folding of overbets, a position leak, a time-bank effect. Data and scripts are reproducible; opponent set is DEV only (seeds 6000-6129).
