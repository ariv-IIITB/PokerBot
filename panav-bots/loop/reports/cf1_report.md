# CF1: counterfactual replay of single decisions (final_seeded vs new_eqrandom, lakshya1)

Tool: `panav-bots/loop/tools/cf_replay.py` (`validate`, `knownanswer`, `run`, `report`). Raw rows: `panav-bots/loop/results/cf1/`.
Logs: 30 pairs x 200 h, `--first-seed 7000` (final_seeded vs eqrandom +0.51+-0.20 c/h; vs lakshya1 +0.43+-0.25 c/h, 0 forfeits).
MATCH WINS (duplicate pair = match, Stage 1 200h legs, base final_seeded only): vs eqrandom 20/30 = 67%; vs lakshya1 17/30 = 57%.
This report measures single decisions, not candidate matches, so there are no candidate match wins.

## How it works
Deal = `deck_for(seed, hand_id-1)`; leg 1 has A=SB in even h, leg 2 in odd h. One decision is replayed with the lab engine: BOTH sides are
scripted from the log up to the decision (our actions + discard, the OPPONENT's actions + discard, so we condition on the exact logged
state even for a random opponent), our player plays the forced action (fold/call/check/raise-to X), then the real bots play on live.
Both are fresh subprocesses per replay. Value = our chips for the whole hand (blinds in), mean over N replays. A check (`state_ok`)
compares pot/to_call/stack at the forced action with the log; 0 errors, 0 dropped replays in all runs.
`--ours-seeds 10`: replay i uses a build with `sample_seed` i (our sampling is keyed by the deal, so otherwise N replays are identical).
`--warm`: also feed ours the logged stream and the opponent our logged actions for hands 0..h-1 (keeps in-match learning; 60-90 s per decision).

## Validation
(a) Deal and engine: all-scripted replay reproduces hole cards and net chips in 240/240 hands (lakshya1 logs, 60 h x4) and 400/400 (200 h x2).
    Opponent live in ONE persistent process fed the whole leg (ours scripted): lakshya1 reproduces its own actions and the net in 400/400
    hands (fixed RNG seed 987654321: deterministic); new_eqrandom 99/100 (one MC-noise mismatch). A FRESH lakshya1 per hand: only 22-28/60
    hands identical -> its play depends on RNG-stream position / learned state, so fresh-start replays draw from its mixing, not from the match's draw.
(b) Known answer, 20 river decisions facing a bet (9 we win at showdown, 9 we lose, 2 ties): forced FOLD = -(chips in) 20/20; forced CALL =
    +opp stake if we win / -(stake+call) if we lose 20/20 (expected value from `rules().evaluator` on the engine's own cards).

## What is lost / biases (read before using the numbers)
1. In-match learning of BOTH bots (our exploit layer SPRT traits, opponent models) is lost in the default (cold) mode. Check = replay of the
   LOGGED action vs the logged net: classes i/iii reproduce it for 75-100% of decisions; class ii (call, then later streets) only 35-62%.
   Warm start on the same 30 class-ii decisions: fold-gain +44.6+-17.6 (warm) vs +64.1+-19.3 (cold) vs eqrandom, -50.3+-16.5 vs -55.2+-16.3
   vs lakshya1: cold OVERSTATES "fold is better" by ~5 (lakshya1) to ~20 (eqrandom) chips in class ii; signs unchanged. Cold numbers below
   for class ii are therefore an upper bound for FOLD.
2. Selection bias: the logged action is the blueprint's own mixed action, so "alt beats logged" means "a pure always-X rule beats the
   blueprint's mixture at those nodes"; a gain says the mixture is wrong against THIS opponent, not that it is wrong in equilibrium. Classes are
   chosen by the logged action (folds, big calls, check-behinds), and sampling is 150 random decisions per class and opponent from 4320/2506/1764 (lakshya1)
   and 1470/503/1783 (eqrandom) candidates.
3. Per-decision SE = spread over the 10 sampling-seed replays (floor 0.5 chip); it ignores which of our mixed lines the match really drew, so
   "share where alt beats logged by > 1 SE" is generous. Use the mean gain +- SE over decisions (the SE below), which is a proper SE.
4. Chip units are per decision (chips to end of hand), not per hand. Equity bucket = our equity vs a random hand (bot.equity; flop: best of
   the 3 discards). Alternatives: i = call, ii = fold, iii = bet the smallest tree size (turn/river pot/2, >= min raise).

## Results (seeds run: cold, 10 sampling seeds; n = 150 decisions per cell)
| class, opponent | alt beats logged >1SE | logged beats alt >1SE | gain of always switching (chips/decision) |
|---|---|---|---|
| i fold -> CALL, eqrandom | 6% | 91% | -30.5 +- 4.7 (every bucket negative: folds are right) |
| i fold -> CALL, lakshya1 | 51% | 47% | +4.0 +- 6.5 (nothing) |
| ii bigcall -> FOLD, eqrandom | 81% | 19% | +19.7 +- 8.9 (upper bound, see 1; warm n=30: +44.6 +- 17.6) |
| ii bigcall -> FOLD, lakshya1 | 37% | 63% | -5.5 +- 6.3 (calls are right; warm n=30: -50 +- 17) |
| iii check -> BET, eqrandom | 36% | 21% | -0.3 +- 1.8 |
| iii check -> BET, lakshya1 | 51% | 45% | +4.6 +- 3.7 |

By hand strength (gain per decision, alternative minus logged; n in brackets):
- i fold->call: eqrandom <0.4 -25.6 (43), 0.4-0.55 -32.4 (56), 0.55-0.7 -32.1 (41), 0.7-0.85 -34.8+-37 (10); lakshya1 <0.4 -6.3+-6 (40),
  0.4-0.55 +4.8+-11 (53), 0.55-0.7 -3.5+-16 (31), 0.7-0.85 +20+-22 (25). Pooled eq>=0.7: +10+-20 (36): no evidence.
- ii call->fold: eqrandom 0.7-0.85 **+45.0+-10.5 (59)**, 0.55-0.7 +14+-11 (25), >0.85 -6.9+-22 (49); lakshya1 0.55-0.7 -12.3+-6.6 (36),
  0.7-0.85 +9.3+-11 (63), >0.85 -28.5+-16 (35). Only vs eqrandom does calling a >= 0.7-pot bet with 0.7-0.85 equity lose clearly.
- iii check->bet: **eq >= 0.7 pooled +11.1+-2.9 (124)**: eqrandom 0.7-0.85 +2.6+-1.4 (58), >0.85 +25+-14 (7); lakshya1 0.55-0.7 +9.0+-7.7 (48),
  0.7-0.85 +12.6+-6.5 (44), >0.85 +33+-9 (15). eq < 0.7 pooled -4.1+-2.7 (176); lakshya1 < 0.55: bet loses -17 to -20 (43): do not bluff.

## Reading
- Our folds on flop/turn are fine (eqrandom: strongly; lakshya1: neutral). No fold leak found.
- Big-bet calls: one clear leak, vs eqrandom only (value-heavy bettor), in the 0.7-0.85 bucket; not present vs lakshya1. Needs a trait gate
  (opponent bet frequency vs value density) and the warm estimate says it is about half as large as the cold one.
- Check-behind with strong hands (eq >= 0.7) loses chips against both opponents (+11 chips per decision for betting, 124 of 300 sampled
  check-behinds, SE 2.9, signs agree on both opponents and across buckets); weak hands should keep checking. Principle (value-bet instead
  of slow-playing vs opponents that do not punish it) is general, but the logged check is the blueprint's trap mix: needs the Ivey test and a
  paired match check on unseen bots before any change.
- Not done: warm start for classes i/iii (they reproduce the log at 75-100% cold); opponents other than these two; N per decision is 10-20, not 30-50.

## Cost
Cold: 450 decisions x ~10-20 replays ~ 19 min per opponent on 3 cores; warm: ~1 min per decision per core.

## Follow-up: 4 more opponents, classes ii and iii, opponent traits (13 Nov)
Logs: 30 pairs x 200 h, seeds 7200-7229 (eqrandom/lakshya1: 7000-7029, from above). Cold runs: `--ours-seeds 10`, 150 decisions per class
(new_minraise: only 82 big calls exist). Class iii sampled with `--min-eq 0.7` (eqrandom/lakshya1: the eq >= 0.7 rows of the earlier unfiltered
sample). Warm runs: 30 class-ii decisions per opponent (a different random sample from the cold 150, except for eqrandom/lakshya1).
Traits come from `panav-bots/loop/tools/opp_traits.py` on the same logs: flop bet = the opponent's first flop action with no bet before it is
a bet; big/100 = bets/raises of at least 0.7 pot we faced on flop/turn per 100 hands that reached the flop; big share = share of the flop/turn
bets we faced that were big; value share = in hands where we CALLED a big bet and reached showdown, the share where the opponent's hand beat
ours (n sd = number of those showdowns). Gains are in chips per decision (alternative minus logged), mean +- SE over decisions.
Base MATCH WINS = duplicate pairs won by final_seeded, Stage 1 (200 h legs). No Stage 2 legs were played.

| opponent | base chips/h | MATCH WINS | flop bet | big/100 flop hands | big share | value share (n sd) | ii fold-gain cold (n) | ii warm n=30 | ii eq0.7-0.85 cold (n) | iii bet-gain eq>=0.7 (n) |
|---|---|---|---|---|---|---|---|---|---|---|
| new_minraise | +0.51±0.24 | 20/30 (67%) | 0.38 | 2.6 | 0.04 | 0.77 (73) | +5.5±9.8 (82) | -0.5±11.7 (30) | +15.2±10.8 (39) | +2.4±2.3 (150) |
| new_exploiter | +0.39±0.16 | 18/30 (60%) | 0.40 | 17.2 | 0.30 | 0.72 (262) | +12.7±7.3 (150) | +25.0±7.8 (30) | +24.2±10.1 (60) | +5.8±1.8 (150) |
| new_eqrandom | +0.51±0.20 | 20/30 (67%) | 0.29 | 16.6 | 0.32 | 0.67 (228) | +19.7±8.9 (150) | +44.6±17.6 (30) | +45.0±10.5 (59) | +5.0±2.0 (65) |
| conv_opp3 | +0.21±0.23 | 15/30 (50%) | 0.62 | 31.5 | 0.37 | 0.55 (499) | -8.3±7.1 (150) | +5.3±12.2 (30) | +1.7±11.5 (50) | +4.8±2.8 (150) |
| new_geometric | +0.49±0.24 | 18/30 (60%) | 0.34 | 48.2 | 0.92 | 0.42 (489) | -20.7±8.6 (150) | -50.2±17.9 (30) | +10.9±13.4 (53) | +9.7±1.9 (150) |
| lakshya1 | +0.43±0.25 | 17/30 (57%) | 0.64 | 67.6 | 0.82 | 0.42 (888) | -5.5±6.3 (150) | -50.3±16.5 (30) | +9.3±11.1 (63) | +17.8±5.5 (59) |

- **Trait for class ii (fold big calls): the value share of the opponent's shown big bets.** corr(value share, cold fold-gain) = 0.80 over
  6 opponents. Folding helps vs the value-heavy bettors (exploiter 0.72: +12.7+-7.3 cold, +25.0+-7.8 warm; eqrandom 0.67: +19.7 / +44.6).
  It hurts vs the bluffy ones (geometric and lakshya1 0.42: -20.7 / -50 and -5.5 / -50). It is neutral vs conv_opp3 (0.55) and minraise (0.77,
  only 2.6 big bets per 100 flops, n small). The bluffy opponents also show a high big share (0.82-0.92) and high big/100 (48-68); the
  value-heavy ones show a low big share (0.30-0.32) and big/100 of about 17. Either is a usable within-leg gate: a big share <= ~0.4 with
  value share >= ~0.65 means fold more, a big share >= ~0.8 means call. The value share needs about 30+ showdowns to estimate; the big share
  is visible from the first hands.
- **Class ii is also strength-dependent on every opponent:** calling with eq 0.7-0.85 loses to folding vs all 6 (+1.7 to +45; significant
  vs eqrandom and exploiter only). Calling with eq > 0.85 is right vs all 6 (fold-gain -6.9 eqrandom, +0.3 exploiter, -28 to -80 elsewhere).
  A gate should therefore fold only the 0.7-0.85 calls, and only vs a low-big-share / high-value-share opponent.
- Class ii fidelity (cold replay of the logged call reproduces the logged net): 39-66% on the new 4, so cold class-ii numbers carry the
  learning-loss bias described above. Where the warm sample (n=30) is available it agrees in sign with cold for 5 of 6 opponents (conv_opp3
  goes from -8.3 to +5.3, both within noise).
- **Class iii (bet instead of check-behind, eq >= 0.7): positive vs all 6 opponents** (+2.4+-2.3 minraise, +4.8+-2.8 conv_opp3, +5.0+-2.0
  eqrandom, +5.8+-1.8 exploiter, +9.7+-1.9 geometric, +17.8+-5.5 lakshya1); more than 2 SE on 4 of 6. The gain is largest for eq > 0.85
  (+4.6 to +33) and largest vs the bluffy, high-aggression opponents. Fidelity is 75-92%. This supports VAL1 as a general change rather than a
  trait-gated one; it still needs a paired match check on unseen bots, since the logged check is the blueprint's trapping mix (selection bias).
