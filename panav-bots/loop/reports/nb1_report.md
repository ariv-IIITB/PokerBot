# NB1: final vs new_eqrandom at 500-hand legs. VERDICT: FAIL (no passing change; ship final unchanged)

## PASS rule (pre-registered before any candidate number)
- DEV (new_eqrandom, seeds 800-815, 500h): paired delta cand-base > 2 x SE of the base-vs-base noise floor.
- Guards (seeds 900-911, 200h): pooled delta >= 0, no bot down > 2 SE, head-to-head cand vs base not worse; no forfeits.
- DEV failed, so the guard batches were NOT run (budget: 15 bots x 2 bots x 12 pairs ~ 2 h). Nothing is promoted.

## 1. Reproduction and noise floor (final vs new_eqrandom, 500h legs, real bank, 16 pairs)
| run | seeds | chips/hand | score |
|---|---|---|---|
| repro | 700-715 | -0.26 +- 0.34 | 0.312 |
| base run1 | 800-815 | -0.24 +- 0.25 | 0.469 |
| base run2 (same seeds) | 800-815 | +0.15 +- 0.22 | 0.531 |
Earlier: -0.95 +- 0.23 (600-611), -0.46 +- 0.31 (400-407). Pooled about -0.3; the loss is real but smaller than first measured.
Noise floor: run2-run1 paired delta +0.395 +- 0.195 (SD per seed 0.78). final's solver is wall-clock driven, so a 16-pair single-bot
delta under ~0.4 chips/hand is noise. The 100-hand window breakdown is also noisy (no clean fade over the leg).

## 2. Diagnosis (tools/nb1_diag.py on the logs; "EV" = net chips of the hand minus what folding at that point would have cost)
new_eqrandom: bets 0.33/0.5/0.75/1.0 pot by equity vs random (big = high equity), never bluffs, never folds a hand it bet to a raise.
Big bets (>= 0.7 pot) are only 9-13 % of its decisions; it folds to our flop/turn/river bets 44/39/64 %.
- Where the chips go (repro): showdown losses -61.8k, our folds -48.5k (river -20k), vs showdown wins +72.5k, its folds +33.6k.
- Its small bets (< 0.7 pot): our calls earn +6 (flop) to +53 (river) each; our raises over them earn +33..+57. Not a leak.
- LEAK 1 (robust, 4 seed sets): calling its big flop/turn bets. n = 360-400 flop, 280-340 turn per 16 pairs; EV -13..-19 and -4..-20 per
  call, win 13-18 %. Sum -4k..-7.6k flop and -1.4k..-5.7k turn per 16000 hands (about -0.4..-0.6 chips/hand). Shape: 60 % are
  "call, then fold a later street" (-20 each); showdowns split about 43 % wins at +177 vs 57 % losses at -151 (roughly even).
  River calls of big bets are about break-even (+2..+17 each, win 23-26 %): not a leak.
- LEAK 2 (seed-dependent): our raises over its big bets. Seeds 700-715: river -7.8k (108 raises, -72 each, win 20 %: second-best flush,
  low sets, all-ins it calls or re-raises). Seeds 800-815: river -1.1k..-1.9k (about 95 raises, -7..-20 each). So about 2/3 of that
  loss was luck of the cooler draws. It never folds to our raise over a big bet (0/52, 0/108, 0/28 folds; re-raises 20-50 %).
- Our bluffing into its calls is NOT a leak: it folds to our river bets 64-75 %, first-in bets called earn +8 flop, +16 turn, +22 river.
  The station/riverbluff moves correctly stay off (its river call rate 0.32, not a station); rivernarrow is on and does not stop LEAK 2.

## 3. Moves tried (both gated, bounded, auto-off; files panav-bots/loop/cand/nb1_a.py, nb1_b.py)
Trait "committed" = it keeps its bet when we raise over it (fold rate under ~10 % vs ~35 % for a balanced bettor).
- bigraise: facing a >= 0.7 pot bet with trait on: flop/turn raises of non-nut buckets (< 0.93 percentile) become call (fold under 0.5);
  river: solver opp range becomes the top slice of its river-start range sized by its rate of bets at least that big (5-35 %).
- bigfold: flop/turn buckets under the 0.50 percentile fold more to a big bet (call -> fold, share 0.6 x strength).
- A: SPRT gate (p0 0.65 keep, p1 0.92). Replay of the logs: it says "yes" around hand 130-490 (mean ~300) of 500, so it acts in the
  last 40 % of a leg only, on ~3 raises over big bets a leg. B: soft Bayesian strength (prior fold rate 0.30, weight 6), fires from ~4 raises.
## 4. DEV result (seeds 800-815, 500h, paired vs the two base runs)
| cand | chips/hand | vs run1 | vs run2 |
|---|---|---|---|
| A (bigraise) | -0.09 +- 0.21 | +0.16 +- 0.13 | -0.24 +- 0.19 |
| B (bigraise+bigfold) | -0.09 +- 0.24 | +0.16 +- 0.17 | -0.24 +- 0.15 |
Base mean of the two runs -0.05. Both candidates sit inside the noise floor (< 0.4): FAIL by the pre-registered rule.
Mechanism check (cb logs): flop big-bet calls 378 (base 378-398), turn 318 (327-342), river big raises 80 (92-97 base): the moves barely
changed the decisions, so there is nothing to measure. LEAK 1's calls come from buckets the 0.50-percentile fold shift does not reach, or
the shift is capped (TV 0.3) and the strength is low. I did not find which; not enough budget to look.

## 5. Ivey test
"A guy who never folds to a re-raise and bets big only when he has it: I stop bluff-raising him and I stop paying off with draws and
second pair. I do not need to see his cards to know it. But if he starts bluffing big, my folds get picked off, so I watch showdowns."
- bigraise: PRINCIPLE for the raise side (clean maths: no fold equity => raise only if ahead of his range), SITUATIONAL as a move (gate
  fires late, small n), exploitable back by a bettor who bluffs big but never folds to raises (rare); bounded by shift <= 0.8, TV 0.3.
- bigfold: SITUATIONAL; no showdown evidence that the big flop/turn bets are value (the showdown bluff index, we win 28 % of shown big bets,
  is near the balanced 1/3, so a showdown gate would not fire). It rests on one bot's data: OVERFIT risk. Not promoted.
## 6. What would work next (not done)
LEAK 1 is a call-then-give-up chain: decide on the flop whether the hand can continue against a big turn bet (planned fold, not a
bucket-percentile shift). Needs the bucket-level view of those calls (log the bucket and the blueprint call/fold mix in the bot) first.
Seeds used: 700-715 repro, 800-815 DEV; ledger lines added to results/SEEDS.md. Guards 900-911 unused. Branch loop/nb1.
