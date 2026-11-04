## anti_aggro: family d_new_lag, maniac; defaults aa_call_margin=-0.03, aa_mdf_mult=1.1, aa_bluff_mult=0.5

### Descent round 1 (seeds 51600-51629, 30 pairs, locks off)
centre aa_call_margin=-0.03, aa_mdf_mult=1.1, aa_bluff_mult=0.5: d_new_lag +4.61±0.42, maniac +51.51±0.91 | sum +56.12
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| aa_call_margin | -0.06 | +1.78 ± 1.30 | +1.4 |
| aa_call_margin | 0 | -1.80 ± 1.24 | -1.4 |
| aa_mdf_mult | 1 | +1.96 ± 1.29 | +1.5 |
| aa_mdf_mult | 1.2 | +0.43 ± 1.29 | +0.3 |
| aa_bluff_mult | 0.25 | +0.40 ± 1.26 | +0.3 |
| aa_bluff_mult | 0.75 | +0.06 ± 1.29 | +0.0 |
**move** aa_mdf_mult -> 1 (diff +1.96, z +1.5)

### Descent round 2 (seeds 51630-51659, 30 pairs, locks off)
centre aa_call_margin=-0.03, aa_mdf_mult=1, aa_bluff_mult=0.5: d_new_lag +5.22±0.49, maniac +53.30±0.85 | sum +58.52
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| aa_call_margin | -0.06 | -0.74 ± 1.34 | -0.6 |
| aa_call_margin | 0 | -3.35 ± 1.24 | -2.7 |
| aa_mdf_mult | 0.9 | -1.53 ± 1.25 | -1.2 |
| aa_mdf_mult | 1.1 | -0.51 ± 1.35 | -0.4 |
| aa_bluff_mult | 0.25 | -1.45 ± 1.26 | -1.1 |
| aa_bluff_mult | 0.75 | +2.13 ± 1.38 | +1.5 |
**move** aa_bluff_mult -> 0.75 (diff +2.13, z +1.5)

### Descent round 3 (seeds 51660-51689, 30 pairs, locks off)
centre aa_call_margin=-0.03, aa_mdf_mult=1, aa_bluff_mult=0.75: d_new_lag +5.63±0.59, maniac +52.64±0.68 | sum +58.27
| parameter | value | sum diff vs centre ± SE | z |
|---|---|---|---|
| aa_call_margin | -0.06 | -0.67 ± 1.30 | -0.5 |
| aa_call_margin | 0 | -2.76 ± 1.15 | -2.4 |
| aa_mdf_mult | 0.9 | -1.04 ± 1.39 | -0.7 |
| aa_mdf_mult | 1.1 | -0.91 ± 1.28 | -0.7 |
| aa_bluff_mult | 0.5 | -1.50 ± 1.26 | -1.2 |
| aa_bluff_mult | 1 | +0.37 ± 1.38 | +0.3 |
**no move**: best candidate aa_bluff_mult=1 diff +0.37, z +0.3 <= 1

### Grid on aa_call_margin, aa_bluff_mult around aa_call_margin=-0.03, aa_mdf_mult=1, aa_bluff_mult=0.75 (swings aa_call_margin 3.35, aa_mdf_mult 1.96, aa_bluff_mult 2.13; seeds 51700-51729)
| aa_call_margin \ aa_bluff_mult | 0.5 | 0.75 | 1 |
|---|---|---|---|
| -0.06 | -0.35 ± 1.21 (z -0.3) | +0.07 ± 1.24 (z +0.1) | -0.14 ± 1.25 (z -0.1) |
| -0.03 | -1.72 ± 1.25 (z -1.4) | centre | -1.07 ± 1.22 (z -0.9) |
| 0 | -2.54 ± 1.11 (z -2.3) | -2.50 ± 1.14 (z -2.2) | -4.01 ± 1.25 (z -3.2) |
**no grid move** (best other point diff +0.07, z +0.1 <= 1)

Final point: aa_call_margin=-0.03, aa_mdf_mult=1, aa_bluff_mult=0.75 (defaults aa_call_margin=-0.03, aa_mdf_mult=1.1, aa_bluff_mult=0.5)

### Confirmation vs defaults, 50 pairs, seeds 52600-52649, locks off (chips)
```
d_new_lag +5.17 -> +5.76  diff +0.59 ± 0.54 (z +1.1)
maniac   +51.65 -> +51.96  diff +0.31 ± 0.79 (z +0.4)
sum      diff +0.90 ± 0.96 (z +0.9)
verdict: KEEP
```
locks on (score):
```
d_new_lag        0.950 -> 0.990  diff +0.040 ± 0.024
maniac           1.000 -> 1.000  diff +0.000 ± 0.000
overall          0.975 -> 0.995  diff +0.020 ± 0.012 (z +1.7, 2 bots)
verdict: KEEP-score
```
Two-part rule: chips pass (sum +0.90 ± 0.96), score pass -> KEEP

### Restriction vs tier3, 30 pairs, locks off: +0.56 ± 0.23 chips/hand (ok, limit -0.10); match score 0.183 ± 0.050 (info)
VERDICT: KEEP {"aa_call_margin": -0.03, "aa_mdf_mult": 1.0, "aa_bluff_mult": 0.75}
