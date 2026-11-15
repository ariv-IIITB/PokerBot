# PROBEVAL report: raw `probe` (sw_probe) vs base (final_seeded), PRIMARY-METRIC validation — verdict **FAIL (rule 4: head-to-head) — do not ship raw probe**

Pre-registration: `reports/probeval_prereg.md` (committed before any run; not changed). Fresh single-use seeds 30000+ (ledger `results/SEEDS.md`).
Runs: 65 file_duel runs, **0 forfeits, 0 illegal replies**, no `holdout/*` bot opened, `final/bot.py` untouched. Raw data `results/probeval/*.json`, tools `probeval/{run,summ}.py`.
A "match" = one duplicate pair, win if total chips > 0 (draw .5). All deltas cand - base, paired by seed. Per-bot table below.

## Headline (MATCH WINS first)
| test | base W/N | probe W/N | gain |
|---|---|---|---|
| Stage 1, 30 bots x 40 pairs, 200h, POOLED INCL. trapper-type | 752/1200 (62.7%) | 822.5/1200 (68.5%) | **+5.87 ± 1.55 pp** (SE over 40 seeds) |
| same, excl. trapper-type (new_trapper, trapper) | | | +6.65 ± 1.56 pp |
| Stage 2, 500h legs, lakshya1 + new_eqrandom x 24 pairs | 24/48 (50.0%) | 30/48 (62.5%) | +12.5 ± 6.9 pp (2 bots: evidence only) |
| lakshya1 alone, 500h | 9/24 (38%) | 14/24 (58%) | +20.8 ± 12.0 pp |
| **head-to-head probe vs base, 200h, 40 pairs** | | **6/40 (15%)** (34 losses, 0 draws) | -0.67 ± 0.13 chips/hand |
Chips/hand pooled Stage 1 (cand - base): all **+0.207 ± 0.041**; excl. trapper-type +0.253 ± 0.043. Stage 2: +0.122 ± 0.082 (lakshya1 +0.26 ± 0.16, new_eqrandom -0.02 ± 0.06).

## Pre-registered pass rule
1. Pooled match-win gain incl. trapper-type >= +2.0 pp: **PASS** (+5.87 ± 1.55, 3.8 SE).
2. Pooled chips/hand >= 0: **PASS** (+0.207 ± 0.041).
3. No non-trapper bot down > 2 SE: **PASS** (worst: new_geometric -7.5 ± 9.0 pp, -0.40 ± 0.17 chips = 2.4 SE in chips but not in wins; new_minraise -5.0, s6_discard -5.0, betfold -2.5; none beyond 2 SE of match wins). Trapper-type: new_trapper -17.5 ± 8.7 pp (DOWN > 2 SE, -1.06 ± 0.22 chips/hand) = the adversary cost; spar/trapper is +7.5 ± 9.7 (not hurt).
4a. lakshya1 500h match wins not lower: **PASS** (38% -> 58%).
4b. **Head-to-head cand vs base >= 50% of matches: FAIL (15%, 6/40; -0.67 ± 0.13 chips/hand, ~5 SE).**
5. Zero forfeits/illegal: PASS in the lab (reply-time check not run, see below).

**Overall: FAIL by the pre-registered all-conditions rule, because of 4b.** The trapper-inclusive rule (1) itself passes; the new_trapper loss (-17.5 pp, -1.06 chips; META1 had -25/-46 pp) contributes only -0.6 pp to the pooled average and is more than covered by the gain elsewhere.
Because the overall rule failed, I did NOT build `cands/final_probe.py` or run the INT1-style fuzz/timing/memory/sandbox (the pre-registration says "if rules 1-5 pass"). INT1's `int1_check.py` / `int1_scan.py` are copied into `tools/` and ready if the owner overrides.

## How to read the h2h result (honest caveats)
- It says probe is exploitable BY base: base's own exploit layer (station/prefold/riverbluff/rivernarrow) beats the probing pattern, 34 of 40 matches. That is the same "exploit-back" mechanism as new_trapper, just stronger, and it comes from a bot that is *in our own toolbox*. The tournament field contains bots that exploit like final does; the zoo (30 bots) shows no other bot that does it to this degree, but the zoo is not the tournament.
- Both builds are the seeded eval builds (sample_seed 1), so the two sides draw identical RNG streams; I do not think this biases the outcome (the loss is -0.60/-0.74 chips/hand in both 100h windows) but I did NOT run a base-vs-base h2h noise floor (40 more pairs, ~9 min) to confirm it is ~50%.
- Rule 4b was pre-registered as a hard condition; I did not relax it after seeing the number.

## Per-bot Stage 1 table (full output: `reports/probeval_summary.md`)
|---|---|---|---|---|---|---|
| adapt | 40 | 26/40 (65%) | 26/40 (65%) | +0.0 ± 8.8 | +0.34 ± 0.19 |  |
| betfold | 40 | 35/40 (88%) | 34/40 (85%) | -2.5 ± 6.7 | -0.16 ± 0.20 |  |
| conv_opp3 | 40 | 18/40 (45%) | 30/40 (75%) | +30.0 ± 9.6 | +0.71 ± 0.18 | up>2SE |
| conv_opp4 | 40 | 25/40 (62%) | 29/40 (72%) | +10.0 ± 7.0 | +0.04 ± 0.16 |  |
| discardread | 40 | 24/40 (60%) | 29/40 (72%) | +12.5 ± 8.2 | +0.37 ± 0.18 |  |
| donk | 40 | 22/40 (55%) | 22/40 (55%) | +0.0 ± 7.2 | +0.29 ± 0.19 |  |
| eqtag | 40 | 26/40 (65%) | 28/40 (70%) | +5.0 ± 8.0 | +0.20 ± 0.21 |  |
| lakshya1 | 40 | 20/40 (50%) | 24.5/40 (61%) | +11.2 ± 6.1 | +0.52 ± 0.17 |  |
| light3b | 40 | 18/40 (45%) | 21/40 (52%) | +7.5 ± 7.5 | +0.25 ± 0.23 |  |
| new_eqrandom | 40 | 22/40 (55%) | 27/40 (68%) | +12.5 ± 5.3 | +0.38 ± 0.06 | up>2SE |
| new_exploiter | 40 | 27/40 (68%) | 28/40 (70%) | +2.5 ± 9.1 | -0.03 ± 0.20 |  |
| new_geometric | 40 | 25/40 (62%) | 22/40 (55%) | -7.5 ± 9.0 | -0.40 ± 0.17 |  |
| new_lag | 40 | 30/40 (75%) | 32/40 (80%) | +5.0 ± 9.4 | -0.10 ± 0.44 |  |
| new_minraise | 40 | 24/40 (60%) | 22/40 (55%) | -5.0 ± 7.1 | -0.05 ± 0.20 |  |
| new_rules | 40 | 24/40 (60%) | 24/40 (60%) | +0.0 ± 7.2 | +0.15 ± 0.14 |  |
| new_trapper | 40 | 27/40 (68%) | 20/40 (50%) | -17.5 ± 8.7 | -1.06 ± 0.22 | DOWN>2SE (trapper-type) |
| polar | 40 | 28/40 (70%) | 32/40 (80%) | +10.0 ± 7.0 | +0.04 ± 0.22 |  |
| potctl | 40 | 24/40 (60%) | 27/40 (68%) | +7.5 ± 7.5 | +0.26 ± 0.21 |  |
| s10_regret | 40 | 25/40 (62%) | 28/40 (70%) | +7.5 ± 8.3 | +0.79 ± 0.22 |  |
| s1_ranges | 40 | 40/40 (100%) | 40/40 (100%) | +0.0 ± 0.0 | +0.39 ± 0.03 |  |
| s2_rollout | 40 | 24/40 (60%) | 30/40 (75%) | +15.0 ± 10.5 | +0.42 ± 0.28 |  |
| s3_exploit | 40 | 21/40 (52%) | 29/40 (72%) | +20.0 ± 8.9 | +0.46 ± 0.19 | up>2SE |
| s4_balanced | 40 | 23/40 (58%) | 26/40 (65%) | +7.5 ± 6.6 | +0.43 ± 0.16 |  |
| s5_preflop | 40 | 21/40 (52%) | 27/40 (68%) | +15.0 ± 6.7 | +0.68 ± 0.20 | up>2SE |
| s6_discard | 40 | 23/40 (58%) | 21/40 (52%) | -5.0 ± 8.0 | -0.01 ± 0.17 |  |
| s7_solver | 40 | 22/40 (55%) | 29/40 (72%) | +17.5 ± 9.4 | +0.47 ± 0.26 |  |
| s8_meta | 40 | 24/40 (60%) | 26/40 (65%) | +5.0 ± 8.0 | +0.44 ± 0.17 |  |
| s9_sizing | 40 | 34/40 (85%) | 34/40 (85%) | +0.0 ± 7.2 | -0.05 ± 0.22 |  |
| tilt | 40 | 26/40 (65%) | 28/40 (70%) | +5.0 ± 7.1 | +0.25 ± 0.23 |  |
| trapper | 40 | 24/40 (60%) | 27/40 (68%) | +7.5 ± 9.7 | +0.18 ± 0.21 |  (trapper-type) |

## Recommendation (owner's call)
- Raw probe is a real general improvement against the zoo (+5.9 pp wins / +0.21 chips, 3.8 SE, fresh seeds; META1 +7.2 pp reproduced in direction and size; 25 of 30 bots >= 0 in match wins; the 5 negatives are betfold -2.5, new_minraise -5, s6_discard -5, new_geometric -7.5, new_trapper -17.5) but it loses 85% of matches head-to-head to the base it modifies. If the tournament field resembles our zoo, ship; if it contains a final-like exploiter, it is a liability.
- Cheap next step that would settle it: (a) base-vs-base h2h noise floor (40 pairs); (b) probe vs final-with-exploit-layer-off / vs the other final-family builds (cands) to see which exploit move beats probe; (c) if one move is responsible, gate probe off when the opponent shows that signature (SITUATIONAL, within-leg), then re-run the same PRIMARY METRIC on new seeds 31000+.
