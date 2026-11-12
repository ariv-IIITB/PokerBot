# Track L1 report: take the initiative (probe move)  — verdict PARTIAL

## Move (cand `panav-bots/loop/cands/l1_probe2.py`, source `panav-bots/loop/src_l1/botsrc.exploit.py`)
`probe`: new trait `weakcheck` (SPRT p0 0.40 / p1 0.60): opponent folds to our bet in spots where it checked to us first (any post-flop street).
Principle: a bet of s pot breaks even as a bluff at s/(1+s) (0.375 at 0.6 pot); a checking range is weak. When "yes", shift up to 0.5*strength of our
check mass (opp checked this street, to_call 0) to a bet already on offer (blueprint sizeA/B, else sizeA; river: the solver's own raise labels only).
Ramps in via SPRT, switches off via CUSUM, TV <= 0.3 guard. Not used: raising its bets (its fold-to-raise is only 27%, below break-even), no fold->call work.
Diagnosis (base vs lakshya1, 9 seeds x 500): opp folds 51/64/85% (flop/turn/river) after checking vs 37/53/70% when we bet first; we checked behind in 692/626/650 such spots.
First version (existing bet mass only) -0.58; second (create sizeA) -0.20 (base -0.92) on dev.

## Ivey test
"When a tight-checking opponent folds 64-85% to my bets after it checks, I fire every time it checks and keep a few traps. If it starts to
check-raise, I see the folds drop and stop." PRINCIPLE, gated on the observed fold rate and unwound by CUSUM. Exploit-back (adversaries/ script): NOT run.

## Paired numbers (cand - base, chips/hand; SE of delta ~ sqrt(se_a^2+se_b^2); solver is wall-clock driven so reruns differ by ~±1 on 16 pairs)
| set | base | cand | delta |
|---|---|---|---|
| lakshya1 dev seeds 1-9, 500-hand legs | -0.92±0.21 | -0.20±0.33 | +0.72 ±0.39 |
| lakshya1 confirm seeds 10-27 (run once; base ran twice: -0.44, -0.45) | -0.45±0.20 | -0.18±0.24 | +0.27 ±0.31 |
| aggressive set (16 pairs, 200h): s2_rollout / s3_exploit / eqtag / new_lag | +0.11/+0.58/+0.80/+3.51 | -0.14/+0.03/+0.46/+2.75 | -0.25/-0.55/-0.34/-0.76 (noise: a rerun of new_lag gave base +2.40, cand +3.56) |
| guard set (10 pairs, 12 bots) | mean +0.78 | mean +0.80 | mean +0.02 (range -0.90..+0.84) |
| final holdout, head-to-head cand vs base | not run (time) | | |

## Mechanism
In logs (cand vs lakshya1) our bets after an opp check rose flop 872->975, turn 525->655 (river 319->449 in v1), fold rate achieved 49/61/88%,
avg net of those bets +3.1/+11.6/+25.7. Against new_lag the gate stayed mostly off (fold-after-check 12/24/63%, bets 322->346). Counters inside the bot
are in `summary()["probe"]` (stderr, not captured by file_duel); mechanism above is from the hand logs.

## Honest read
Dev +0.7 and confirm +0.3 point the right way but confirm is under 1 SE; the aggressive set is noisy and negative on 4 of 4 in the first run, contradicted by a rerun. Guard flat.
Not shown to beat lakshya1 (still -0.18 ±0.24). Needs more pairs, the aggressive set rerun, holdout, and an exploit-back adversary before any ship decision.
