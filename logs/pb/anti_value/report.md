## anti_value: family d_new_minraise, d_new_trapper; defaults x_vo_margin=0.12, av_raise_fold_eq=0.6

### Descent round 1 (seeds 51300-51329, 30 pairs, locks off)
centre x_vo_margin=0.12, av_raise_fold_eq=0.6: d_new_minraise +0.58±0.16, d_new_trapper +0.77±0.19 | sum +1.35
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| x_vo_margin | 0.06 | +0.01 ± 0.36 | +0.0 |
| x_vo_margin | 0.18 | +0.03 ± 0.38 | +0.1 |
| av_raise_fold_eq | 0.5 | -0.38 ± 0.34 | -1.1 |
| av_raise_fold_eq | 0.7 | +0.56 ± 0.36 | +1.6 |
**move** av_raise_fold_eq -> 0.7 (diff +0.56, z +1.6)

### Descent round 2 (seeds 51330-51359, 30 pairs, locks off)
centre x_vo_margin=0.12, av_raise_fold_eq=0.7: d_new_minraise +0.62±0.15, d_new_trapper +1.38±0.21 | sum +2.00
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| x_vo_margin | 0.06 | -0.07 ± 0.36 | -0.2 |
| x_vo_margin | 0.18 | -0.07 ± 0.38 | -0.2 |
| av_raise_fold_eq | 0.6 | -0.48 ± 0.37 | -1.3 |
| av_raise_fold_eq | 0.8 | +0.68 ± 0.38 | +1.8 |
**move** av_raise_fold_eq -> 0.8 (diff +0.68, z +1.8)

### Descent round 3 (seeds 51360-51389, 30 pairs, locks off)
centre x_vo_margin=0.12, av_raise_fold_eq=0.8: d_new_minraise +0.38±0.15, d_new_trapper +1.98±0.24 | sum +2.36
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| x_vo_margin | 0.06 | -0.27 ± 0.40 | -0.7 |
| x_vo_margin | 0.18 | -0.40 ± 0.41 | -1.0 |
| av_raise_fold_eq | 0.7 | -0.55 ± 0.38 | -1.5 |
| av_raise_fold_eq | 0.9 | +0.12 ± 0.37 | +0.3 |
**no move**: best candidate av_raise_fold_eq=0.9 diff +0.12, z +0.3 <= 1

### Grid on av_raise_fold_eq, x_vo_margin around x_vo_margin=0.12, av_raise_fold_eq=0.8 (swings x_vo_margin 0.40, av_raise_fold_eq 0.68; seeds 51400-51429)
| av_raise_fold_eq \ x_vo_margin | 0.06 | 0.12 | 0.18 |
|---|---|---|---|
| 0.7 | -0.86 ± 0.36 (z -2.4) | -0.58 ± 0.33 (z -1.8) | -0.44 ± 0.34 (z -1.3) |
| 0.8 | +0.07 ± 0.35 (z +0.2) | centre | +0.18 ± 0.36 (z +0.5) |
| 0.9 | +0.05 ± 0.37 (z +0.1) | +0.19 ± 0.37 (z +0.5) | +0.21 ± 0.37 (z +0.6) |
**no grid move** (best other point diff +0.21, z +0.6 <= 1)
