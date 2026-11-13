# META1: adaptive switch controller — verdict **FAIL (no controller shipped)**; side finding: raw `probe` is positive on average

Switches (forced = raw, ungated, strength 1, built from final's unpacked sources + the L1/VAL1/B1/CALL1 patches merged into ONE exploit layer;
`meta1/mk_build.py`, builds in `meta1/builds/sw_*.py`; seeded like final_seeded): probe (L1), foldall (B1), valuebet (VAL1, bet/raise with top-25% buckets),
potfold (CALL1 module with gate+ledger off, p=.75, cut .9). Base = `evalbuilds/final_seeded.py`. Sanity: each switch fires (touched counters checked).
Data: 30 bots (all ZOO folds + Opps/discard + strong/spar + lakshya1; **no sealed holdout opened**), 24 pairs x 200h, seeds 13000-13023, paired by seed,
base and the 4 switches, 150 runs, 0 forfeits. s1_ranges is a degenerate folding bot (base wins 24/24): excluded from fits. Seed ledger: 13000-13023 table, 14000-14023 probe replication.
CALL1 v3 (big-bet-frequency gate) was NOT added: it needs integration into this build, not cheap; potfold here is the raw v1 module.

## (1) Effect table (full 30x4 with SE: `reports/meta1_effect_table.txt`; per-bot JSON `results/meta1/*.json`)
Pooled over 29 bots, cand - base, mean of per-bot deltas (SE across bots); match wins: one pair = one match.
| switch | dwin (pp) | dchips/hand | pooled match wins base -> cand (29 bots x 24) |
|---|---|---|---|
| probe | **+7.2 ± 2.0** | **+0.31 ± 0.07** | 63.1% -> 70.3% |
| potfold | +4.0 ± 2.5 | +0.13 ± 0.08 | 63.1% -> 67.0% |
| valuebet | -1.6 ± 2.0 | -0.04 ± 0.07 | 63.1% -> 61.5% |
| foldall | **-8.6 ± 2.3** | **-0.34 ± 0.07** | 63.1% -> 54.5% |
Per-bot SE of dwin is 8-12 pp (24 matches): only a handful of single-bot effects exceed 2 SE. Probe by fold: F1 +13.2, F2 +7.1, F3 +5.7, F4 +4.2 pp (positive in all four).
Real heterogeneity seen only for probe: new_trapper -25.0 ± 9.0 pp / -1.03 chips (exploit-back by a trapper); also positive outliers conv_opp3/conv_opp4/lakshya1/s5_preflop (+17..+25 pp).
potfold: lakshya1 +37.5 pp (+1.12), new_exploiter +25, new_eqrandom +21, s5_preflop +21, but betfold -12.5, s10_regret -12.5.

## (2) Traits (`meta1/traits.py`, `results/meta1/traits.json`): first N=60 and N=100 hands of a leg, from the 24x2 base logs
Observable only: first-in bet rate by street, fold rate to our bets by street, raise-when-facing rate, big-bet (>=0.7 pot) share, preflop open / fold-to-open / 3bet,
check-raise rate, showdown value share (opp beat us when it bet / bet big). Caveat: 12 of the 30 bots have near-identical trait vectors (clones of final's family,
e.g. fb .52 fold .41 raise .03), so there are only ~18 distinct opponent profiles for the fit.

## (3) Oracle ceiling (hindsight per-bot on/off vs split-half corrected: choose on even seeds, score on odd seeds and vice versa)
| switch | always-on | oracle (in-sample) | oracle (split-half, honest) |
|---|---|---|---|
| probe | +7.2 pp | +8.8 | **+4.7** |
| potfold | +4.0 | +7.3 | **+2.2** |
| valuebet | -1.6 | +3.3 | **-1.0** |
| foldall | -8.6 | +1.6 | **-1.3** |
After removing selection noise NO switch has a positive per-bot-choice ceiling above the best fixed policy (probe/potfold: always-on is already above the honest oracle;
valuebet/foldall: best is off). So per-opponent selection has no measurable value beyond "on" or "off" for the whole field at 24 pairs/bot.

## (4) Gating rules, leave-one-bot-out CV (`meta1/cv.py`; single monotone threshold or 2-feature AND, default OFF, N=60 and N=100 agree)
dwin gain vs always-off (pp): probe 1-feat +5.75 ± 1.84 (always-on +7.18); potfold +4.02 ± 1.67 / 2-feat +3.16 (always-on +3.95);
valuebet -3.0 (worse than off); foldall -2.2. In chips: probe +0.30 (always-on +0.31), potfold +0.08/+0.16 (always-on +0.13), valuebet +0.05, foldall 0.00.
The rule picked in 26/29 folds for probe was "sd_value <= theta" (opponent rarely beats us when it bets), for potfold "fold_flop >= theta"; both are unstable proxies
(different features in the stray folds) and neither beats the constant policy. **Gated gain does not exceed always-on/always-off => by the brief, stop: no controller implemented (step 5), sealed holdouts NOT run (step 6).**
Why it fails: one negative bot (new_trapper) is the only strong anti-probe signal; LOBO cannot learn a rule from a single example, and a rule hand-fitted to it is overfit by construction.

## Side finding — probe replication on fresh seeds 14000-14023 (24 pairs x 200h, F4 fold + new_trapper, base vs forced probe)
F4 (8 bots): **+8.3 ± 5.2 pp** match wins (127.0 -> 143.0 of 192 = 66.1% -> 74.5%), +0.25 ± 0.15 chips/hand (original run on these bots: +4.2 pp, +0.29).
new_trapper: **-45.8 ± 13.4 pp** (16 -> 5 of 24), -1.72 ± 0.37 chips: the exploit-back loss REPLICATES and is large. With it, all 9: +2.3 ± 7.6 pp, +0.03 chips.
Bots that lose >=10 pp in the replication: donk -12.5, new_exploiter -12.5 (both within 1-1.3 SE). So raw probe is +EV across the field in the table (29 bots +7.2 pp) but a trapper-type
opponent punishes it hard; that is a robustness cost, not a gating success. This contradicts v1's flat pooled result only because v1 tested the trait-gated probe (fires rarely; seeds 5000+).

## Ivey test (for "controller from traits")
"A strong player does adapt, but he adapts on what the opponent SHOWS (it folds to my bets, it never shows down strong when it bets), not on a statistical regression across 30 other opponents;
given 100 hands the evidence per trait is thin and a trapper looks like a station until it springs the trap." Verdict: SITUATIONAL for the within-leg SPRT gates already in final;
a cross-opponent trait->switch table is OVERFIT at this sample size (n=29 bots, effects of 0.1-0.4 chips vs SE 0.2-0.4 each).

## PASS/FAIL: **FAIL** — cross-validated gain over the best constant policy is <= 0 for all four switches; nothing shipped; sealed bots untouched.
Recommendations (owner's call): (a) the actionable item is NOT a controller but a decision on raw probe: +7.2 pp pooled / +0.31 chips (all 4 folds positive, F4 replicated +8.3 pp) vs a replicated -46 pp
against a trapper; run the PRIMARY-METRIC validation of probe (40 pairs x 200h, lakshya1 500h, exploit-back adversary = new_trapper-like) before any ship decision;
(b) foldall should stay off (-8.6 pp), valuebet off, potfold needs CALL1's gate (+4.0 pp raw is not significant, 1.6 SE).
Files: panav-bots/loop/meta1/{mk_build,run_table,run_rep,traits,all_traits,effects,cv,summ}.py, builds/sw_*.py, results/meta1/**, reports/meta1_*.txt.
