## anti_folder: family d_new_exploiter, d_conv_opp3, d_new_rules; defaults x_bluff_max=0.6, x_river_bluff_mult=2.5, x_vo_margin=0.12

### Descent round 1 (seeds 51000-51029, 30 pairs, locks off)
centre x_bluff_max=0.6, x_river_bluff_mult=2.5, x_vo_margin=0.12: d_new_exploiter -0.75±0.21, d_conv_opp3 -1.07±0.31, d_new_rules -0.28±0.20 | sum -2.10
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| x_bluff_max | 0.45 | -1.04 ± 0.60 | -1.7 |
| x_bluff_max | 0.75 | +0.00 ± 0.60 | +0.0 |
| x_river_bluff_mult | 1.5 | -0.83 ± 0.63 | -1.3 |
| x_river_bluff_mult | 3.5 | -0.58 ± 0.60 | -1.0 |
| x_vo_margin | 0.06 | -0.23 ± 0.58 | -0.4 |
| x_vo_margin | 0.18 | -0.25 ± 0.60 | -0.4 |
**no move**: best candidate x_bluff_max=0.75 diff +0.00, z +0.0 <= 1

### Grid on x_bluff_max, x_river_bluff_mult around x_bluff_max=0.6, x_river_bluff_mult=2.5, x_vo_margin=0.12 (swings x_bluff_max 1.04, x_river_bluff_mult 0.83, x_vo_margin 0.25; seeds 51100-51129)
| x_bluff_max \ x_river_bluff_mult | 1.5 | 2.5 | 3.5 |
|---|---|---|---|
| 0.45 | -0.69 ± 0.69 (z -1.0) | -0.65 ± 0.64 (z -1.0) | -0.55 ± 0.63 (z -0.9) |
| 0.6 | -0.94 ± 0.67 (z -1.4) | centre | -0.90 ± 0.64 (z -1.4) |
| 0.75 | -0.47 ± 0.67 (z -0.7) | -0.65 ± 0.64 (z -1.0) | -0.66 ± 0.65 (z -1.0) |
**no grid move** (best other point diff +0.00, z +0.0 <= 1)
