# Zoo map, fold F3 (final = A). Measurement only, no bot edited.
Runs: 24 pairs x 200 hands, `--first-seed 300`, `--processes 3`, logs on. final < +0.5 chips/hand => also 8 pairs x 500 hands, `--first-seed 400`.
No bot needed the 12-pair cut (each 24-pair run took 87-233 s). 0 forfeits anywhere. SE = per-pair SE as printed by file_duel.

| bot | 200h chips/hand +-SE | match score | 500h chips/hand +-SE (8 pairs) | opp flop first-in bet | opp raise vs our bet | final SD win when opp bets |
|---|---|---|---|---|---|---|
| spar/betfold | +0.88 +- 0.23 | 0.708 | - | 0.88 | 0.10 | 0.61 |
| spar/light3b | +0.25 +- 0.46 | 0.500 | +0.37 +- 0.49 (score 0.625) | 1.00 | 0.23 | 0.62 |
| spar/tilt | +0.80 +- 0.41 | 0.479 | - | 0.76 | 0.16 | 0.65 |
| strong/s3_exploit | +0.37 +- 0.23 | 0.542 | -0.03 +- 0.53 (0.562) | 0.70 | 0.08 | 0.61 |
| strong/s7_solver | +0.42 +- 0.25 | 0.542 | -0.10 +- 0.23 (0.312) | 0.69 | 0.08 | 0.56 |
| strong/s9_sizing | +1.99 +- 0.43 | 0.708 | - | 0.70 | 0.09 | 0.68 |
| Opps new_rules | +0.55 +- 0.24 | 0.677 | - | 0.31 | 0.06 | 0.52 |
| Opps new_geometric | +0.27 +- 0.27 | 0.542 | -0.22 +- 0.21 (0.312) | 0.34 | 0.11 | 0.56 |

Mean over the 8 bots (200h): +0.69 chips/hand. Pooled SE ~0.12 (indep. bots).

## Where the chips leak (final's biggest losses, see per-bot files)
- Showdown losses are the largest negative bucket against every bot (-1.7 to -4.7 chips/hand of all hands, offset by showdown wins).
- WE fold @flop/@turn/@river is the next: -0.55 to -1.4 chips/hand-of-all, vs 0.7-1.0 recovered by opp folds.
- Strongest bluffers/aggressors (light3b flop bet 1.00, tilt, s9_sizing): we fold ~1500-2000 flops, costing ~12-14k chips per 9.6k hands.
- Caveat: these are gross buckets, not shown to be leaks; no counterfactual was run.

## Weak spots (honest reading)
- Longer legs are weaker: at 500 hands final is ~0 or negative vs s3_exploit, s7_solver, new_geometric (SE 0.2-0.5, only 8 pairs, so within noise but no edge shown).
- s7_solver and new_geometric 500h match score 0.312.
- light3b, tilt, s3_exploit: match score ~0.5 despite positive chips.
