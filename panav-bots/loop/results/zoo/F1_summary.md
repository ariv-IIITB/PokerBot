# F1 zoo map: final vs fold-F1 bots (24 pairs x 200 hands, first-seed 300)

| bot | chips/hand | SE | match score | 500-hand leg (8 pairs) |
|---|---|---|---|---|
| eqtag | +0.52 | 0.24 | 0.542 | - |
| polar | +1.41 | 0.26 | 0.625 | - |
| s1_ranges | +3.16 | 0.11 | 1.000 | - |
| s5_preflop | +0.48 | 0.24 | 0.542 | +0.21 ± 0.59 chips/hand |
| new_lag | +2.22 | 0.56 | 0.646 | - |
| conv_opp3 | +0.06 | 0.30 | 0.604 | -0.02 ± 0.27 chips/hand |
| lakshya1 | +0.20 | 0.34 | 0.562 | -0.30 ± 0.26 chips/hand |

Notes: measurement only, no bot edited; no forfeits in any run. Bots with final < +0.5 chips/hand got the 500-hand leg. Per-bot leak reports and traits in `<bot>.txt`.
