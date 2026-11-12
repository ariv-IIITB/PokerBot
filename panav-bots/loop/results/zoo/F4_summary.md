# F4 zoo map (final vs each bot; A = panav-bots/final/bot.py)
Measurement only. 200h legs: 24 pairs, first-seed 300. 500h legs: 8 pairs, first-seed 400 (run for all since every 200h result was < +0.5).
No forfeits. Speed: every batch <= 5 min per 24 pairs (no cut to 12 pairs needed).
spar_v4 variants were not run (fold lists the spar/ bots).

| bot | 200h chips/hand ± SE | match score | 500h chips/hand ± SE | match score |
|---|---|---|---|---|
| donk | +0.04 ± 0.32 | 0.500 | +0.13 ± 0.39 | 0.500 |
| adapt | +0.16 ± 0.31 | 0.458 | -0.14 ± 0.24 | 0.375 |
| discardread | +0.44 ± 0.34 | 0.562 | -0.27 ± 0.37 | 0.500 |
| s4_balanced | +0.42 ± 0.25 | 0.479 | -0.25 ± 0.41 | 0.375 |
| s8_meta | +0.36 ± 0.28 | 0.479 | -0.79 ± 0.35 | 0.438 |
| s10_regret | +0.18 ± 0.39 | 0.458 | +0.49 ± 0.36 | 0.625 |
| new_exploiter | +0.25 ± 0.19 | 0.562 | -0.19 ± 0.26 | 0.438 |
| new_eqrandom | +0.35 ± 0.24 | 0.542 | -0.46 ± 0.31 | 0.312 |

Reading: final is positive vs all 8 at 200h but every 200h interval is within ~1-2 SE of 0 except discardread/s4_balanced/new_eqrandom (~1.4 SE).
At 500h the sign flips on 5 of 8 (s8_meta -0.79 ± 0.35 and new_eqrandom -0.46 ± 0.31 the largest); 8 pairs is noisy (SE ~0.3-0.4), so treat as unresolved, not a leak.
Common leak shape in all leak reports: biggest chip loss is showdown losses + folds at turn/river; opponents bet first-in 0.3-0.8 and fold to our river bets 0.7.
Per-bot leak reports and traits: results/zoo/<bot>.txt.
