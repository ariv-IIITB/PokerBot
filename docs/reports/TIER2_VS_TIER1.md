# Why Tier 2 lost to Tier 1 in E7 (Phase F0 investigation, 2026-10-29)

Question: E7 (50 pairs, locks off) had Tier 2 at **−0.64 ± 0.24** (score 0.38) against Tier 1.
Raw logs: `logs/f0/` (ablations `<name>_t1/pool`, confirmation `c_*`, tier1 on the E7 pool `tier1_e7`),
`logs/e7/full.txt` (Tier 2 accounting/profile). Duplicate deals, 400 hands, locks off, `discard_holdem`.

## 1. Tier 1 on the same E7 pool (50 pairs), chips/hand

| Opponent | Tier 1 | Tier 2 (E7) |
|---|---|---|
| tier1 (mirror) | −0.20 ± 0.21 | −0.64 ± 0.24 |
| random_legal | +15.75 ± 0.28 | +22.53 ± 0.37 |
| calling_station | +8.21 ± 0.10 | +8.61 ± 0.11 |
| tight | +8.30 ± 0.28 | +8.16 ± 0.26 |
| maniac | +44.20 ± 0.48 | +51.86 ± 0.52 |
| all_in | +9.02 ± 0.26 | +23.07 ± 0.49 |
| starter | +7.21 ± 0.08 | +7.52 ± 0.10 |
| opp1 | +7.46 ± 0.25 | +7.69 ± 0.22 |
| opp2 | +2.61 ± 0.18 | +2.58 ± 0.19 |
| opp3 | +0.17 ± 0.09 | +0.10 ± 0.07 |
| opp4 | −0.88 ± 0.21 | −0.60 ± 0.17 |

Tier 1 loses to opp4 and ties opp3 too, so those are not Tier 2 regressions. Tier 2's extras add chips
against exploitable bots (random +7, maniac +7.7, all_in +14). Match scores are the same except vs tier1.

## 2. Accounting and profile (E7, Tier 2 vs Tier 1)

Both play 95 % limps preflop. Postflop, Tier 2 **folds less to flop bets** (33 % vs 42 %) and calls more
(53 % vs 45 %); river folds are equal (45 % vs 47 %). Chips: Tier 2 loses the big showdowns
(−8.46 vs +7.79 per hand) and gets back less by folds. Calling lighter against an aggressive opponent
is what the "aggression" shift does. vs opp4 (never bets into raises, folds 83 % to flop bets, folds all
preflop raises) Tier 2 also loses at showdowns (−4.05 vs +2.94).

## 3. Ablations (Tier 2 variants; 100 pairs vs tier1, 30 pairs vs the rest; ± SE; match score)

| Config | tier1 | opp3 | opp4 | starter | maniac |
|---|---|---|---|---|---|
| base | −0.10 ± 0.19 (.49) | +0.17 ± 0.10 (.62) | −0.95 ± 0.30 (.35) | +7.55 | +52.20 |
| `river_bluff_slope` 0 (E4 off) | −0.50 ± 0.18 (.43) | −0.17 ± 0.08 (.35) | −1.12 ± 0.31 (.28) | +7.42 | +52.36 |
| bluff adaptation off | +0.13 ± 0.17 (.53) | −0.02 ± 0.10 (.50) | −0.63 ± 0.25 (.48) | +7.47 | +53.28 |
| value shifts off | −0.21 ± 0.20 (.50) | +0.02 ± 0.09 (.58) | −0.62 ± 0.26 (.43) | +7.18 | +52.12 |
| **`aggr_call_shift` 0** | **+0.30 ± 0.16 (.53)** | +0.16 ± 0.08 (.58) | **−0.16 ± 0.27 (.50)** | +7.58 | +49.48 |
| big-bet pressure shift off | −0.10 ± 0.19 (.50) | +0.16 ± 0.10 (.63) | −0.62 ± 0.20 (.45) | +7.48 | +51.21 |
| all extras off (≈ Tier 1) | +0.15 ± 0.18 (.52) | −0.08 ± 0.11 (.43) | −0.78 ± 0.23 (.42) | +7.12 | +44.16 |

- The 50-pair −0.64 was partly noise: the same base config gives −0.10 ± 0.19 at 100 pairs and −0.22 ± 0.19
  on fresh seeds (pooled ≈ −0.3).
- Turning **E4 off hurts** (−0.4 vs tier1, −0.34 vs opp3): E4 stays.
- All extras off loses 8 chips/hand vs maniac, so the extras are worth keeping as a group.
- One extra stands out: the "call lighter vs aggression" shift (`aggr_call_shift` 0.10).

## 4. Confirmation on fresh seeds (`--first-seed 1000`; 60 pairs main, 30 pairs wide)

| | base | `aggr_call_shift` 0 | difference |
|---|---|---|---|
| tier1 | −0.22 ± 0.19 (.47) | **+0.42 ± 0.22 (.57)** | +0.64 ± 0.29 (2.2 SE) |
| opp3 | +0.17 ± 0.08 (.64) | +0.25 ± 0.08 (.61) | +0.08 |
| opp4 | −0.81 ± 0.18 (.35) | **−0.26 ± 0.16 (.53)** | +0.55 ± 0.24 (2.3 SE) |
| calling_station | +8.86 ± 0.10 | +9.01 ± 0.12 | |
| tight | +8.18 ± 0.29 | +8.27 ± 0.31 | |
| opp1 | +8.02 ± 0.27 (1.00) | +7.48 ± 0.24 (1.00) | −0.54 ± 0.36 |
| opp2 | +2.29 ± 0.20 (.93) | +2.61 ± 0.23 (.93) | |
| maniac | +53.37 ± 0.61 (1.00) | +49.31 ± 0.78 (1.00) | −4.1 ± 1.0 (chips only; score 1.00 both) |

Same direction in both samples for tier1 (+0.40, +0.64) and opp4 (+0.79, +0.55).

## 5. Recommendation

**Fix, not ship Tier 1.** Tier 2's extras pay off as a group (all-off loses 8/hand to maniac and 14/hand
to all_in, and E4 helps vs opp3/opp4/tier1). One of them, `aggr_call_shift`, costs chips against competent
bots: **turned off** (default 0.0, in `tier2.py` and `bot/config/tier2.json`). The exception to the usual
"no opponent drops by more than 2 SE" keep rule: chips vs maniac fall by 4 (4 SE), but we win 100 % of
those matches either way and we optimise for matches, not chips. If a future opponent type shows the shift
mattering, it is one parameter.

Remaining weakness: opp4 is still −0.26 to −0.6 (score ~0.5) and opp3 is a coin flip; both are
Hold'em bots on an adapter. Phase F's real pool decides whether more is needed.
No timing change: package projection at 2x slower is 32-40 % of the bank (limit 50 %).

## 6. A packaging bug found on the way

Upload #2 (`1baec44f…`) was built **without the embedded tables**: the package builder regenerates
`bot/embedded.py` from `data/<variant>/`, which is gitignored and was missing in that container, so it
embedded `ARTIFACTS = {}` (3.8 KB instead of 191 KB). The play is still sound (the tables are a speed-up
for start-of-hand equity) but it is not the bot that was measured. `tools/package_submission.py` now
refuses to build when the committed `embedded.py` has tables and the generated one does not.
Upload #3 (below) has them. Use #3, not #2.
