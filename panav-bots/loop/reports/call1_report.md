# call1: `potfold` (call -> fold vs pot-size bets) -- verdict: FAIL (pre-registered rule, `call1_prereg.md`)
Code: `call1_src/botsrc.potfold.py` (+ small hooks in main/policy/exploit), tools `tools/call1_*.py`, adversary `adversaries/potbluffer.py`,
results `results/call1/`. Candidate = seeded build `cand_v1` (not packaged as `candidates/final_potfold.py`, because FAIL).

## Move
Postflop, facing a bet or raise of 0.75-1.2 pot (D1 size definition, not all-in), when the final move is CALL and the hand's
equity-vs-random proxy (the bot's own S1/max: best keep on the flop, kept pair later) is < 0.90: fold with probability p = 0.75 x g
(every street, both seats). Applied after the policy/solver/exploit layer (a plain call->fold flip; solver range and discard untouched).
Gate: off while the exploit layer's `aggressor` or `riverbluff` SPRT says yes. Ledger (self-correction): realised chips (net + committed,
decision to hand end) of the low-equity pot-size calls we still make; normal-normal shrink to prior mean -15/call (sigma 70, 25
pseudo-calls); g = clip(posterior mean / -15, 0, 1), so winning calls switch the shift off. Honest limit: with p=.75 only ~1-3 calls per
200h leg reach the ledger (about 24 per 500h leg), so the ledger barely moves in Stage 1 and the shift is prior-driven; the trait gate is the
only fast self-correction. Shift bounded: p <= 0.75, only call->fold, never on solver/rule decisions' ranges.

## Dev evidence (7 dev bots, seeds 6000-6059 logs, 168k hands)
Calls of pot-size bets with proxy < .9: n=8078, mean -15.4 chips/call (all 7 bots negative, -10.6..-22.2; flop -13.4/-7.7 button/BB,
turn -26.5/-16.8, river -22.4/-13.0). Proxy .90-.95: +1.3 (n=1072), >=.95: +53.8. First-order gain of folding all: +0.74 c/h (exact for the truncation).
Full-match A/B on seeds 6000-6029: p=.75 pooled +0.32 +- 0.08 (7 bots, wins 127.5 vs 115); p=1.0 on 4 bots +0.79 vs +0.60 for p=.75.

## Validation (22 bots disjoint from dev, seeds 10000-10039, 40 pairs x 200h, paired)
Pooled delta **+0.096 +- 0.049** (z +2.0; need >= +0.15 and >= 1.5 SE: the SE part passes, the +0.15 floor FAILS). Wins 578 vs 567 of 880 (pass).
Per bot (delta +- SE): s7_solver +0.48 .20, s6_discard +0.39 .18, tilt +0.33 .27, light3b +0.31 .23, s3_exploit +0.30 .19, trapper +0.25 .21,
s4_balanced +0.25 .20, conv_opp4 +0.23 .19, new_rules +0.23 .12, s10_regret +0.22 .24, discardread +0.21 .17, adapt +0.20 .18, s8_meta +0.15 .20,
new_trapper +0.12 .20, s1_ranges 0.00, s2_rollout -0.06 .32, s5_preflop -0.09 .23, donk -0.12 .19, betfold -0.14 .16, polar -0.26 .23,
new_lag -0.36 .53, **s9_sizing -0.52 +- 0.25 (z -2.1) -> rule 3 FAILS**. 15 of 22 positive; the shift is real but about 1/3 of the dev gain
(dev numbers were selected on those bots; the first-order +0.74 was an overestimate of what survives opponent response and the gate).
Timing: mean decision 12.96 ms base vs 12.62 ms cand (within 5 ms); 0 forfeits, 0 errors, 0 fallback replies in all runs.

## Other pre-registered arms
- Stage 2, 500h legs, 24 pairs: lakshya1 **+0.87 +- 0.21** (needs >= +0.30: pass; wins 17 vs 10); new_eqrandom +0.45 +- 0.11 (pass).
  Both are dev-type bots, so this is the weaker evidence; but the longer leg gives the trait gate/ledger more data and the sign is the same.
- Head-to-head cand vs base, 40 pairs: **-0.55 +- 0.11 c/h, score .400 -> FAIL (rule 6)**: folding more is exploited by the (otherwise
  identical) base, which bets/bluffs a lot (its own exploit layer is on). This is the direct exploit-back measurement and it is not small.
- potbluffer (stdlib, bets .75-1.0 pot every street, ~50% bluffs, folds to raises): base +6.21, cand +4.77: loss **1.44 +- 0.41 c/h
  vs pooled validation gain 0.10 -> FAIL (rule 7)**. The gate fires (about 60% of eligible spots gated; ledger g .77-1.0) but only after
  the SPRT decides, so the early hands leak; the shift still folds 16 of 68 eligible spots in the ungated hands.

## PASS rule scorecard
1 pooled >= +0.15: FAIL (+0.096). 2 wins: pass. 3 no bot < -2 SE: FAIL (s9_sizing -2.1). 4 lakshya1 500h >= +0.30: pass. 5 eqrandom 500h not worse: pass.
6 head-to-head >= 0: FAIL. 7 potbluffer loss < gain: FAIL. 8 timing/forfeits: pass. => **FAIL; do not ship as is.**
Stage 1 (200h): fails. Stage 2 (500h): both 500h arms pass, but only on dev-type bots and without a Stage 2 validation set -> not enough to ship.

## Ivey test
"When someone bets pot every time, I do not fold less or more by hand rank alone: I fold the middling hands that only beat bluffs
that do not exist, and I call more when I see that bettor is bluffing." Folding bottom-to-middle equity hands against pot-size bets is the
standard price logic (a pot bet needs 33% equity, but these calls realise much less because we are out of position / behind a range that
is value-heavy and our hand plays badly on later streets), so the direction is a PRINCIPLE for static bots. But against a good opponent
who sees us fold 75% of such spots, bets that size become free bluffs: the head-to-head (-0.55) and potbluffer (-1.4) show exactly that
cost, and the within-match defences (trait gate, ledger) are too slow for 200 hands. Verdict: SITUATIONAL -- keep only behind a
strong within-leg trait that the opponent bets pot-size rarely/value-heavily (never as a default), and fold at most ~0.3-0.5; not shippable now.

## Suggested next step (not done)
Gate on the opponent's measured pot-size bet frequency (bets of that size per street opportunity) with a low prior, instead of on
aggressor/riverbluff; try p=0.4 and a shadow ledger from showdowns of called pot bets; re-run the same validation with fresh seeds (10000+ are used up).
