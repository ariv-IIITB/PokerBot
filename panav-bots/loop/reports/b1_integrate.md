# B1 INTEGRATE: verdict FAIL (no change ships). Partial run, see "Not run".

## What I looked for (step 1)
- Exploit layer config was `station,prefold,riverbluff,rivernarrow`. Against the five B1 bots (3-8 legs each, stderr summaries):
  `station`, `riverbluff`, `prefold`, `aggressor` verdicts were "no" in ~every leg, so they never acted. `overfolder` reached "yes" only vs
  s1_ranges (hand 13) and is NOT in CONFIG (so even there it did nothing: touched = {}). Flop+turn folds are pooled in that trait
  (0.25-0.45 vs eqtag/trapper/s2/s3, below its 0.65 bar).
- River: the solver's F-fold best response to the opponent's fold rate already exists, but needs FOLD_MIN_N = 20 answered river bets.
  A 200-hand leg gives 5-22 (typically 10-17): it fired in about 2 of 40 legs. Observed river fold rates 0.6-1.0. This is the under-firing for H1.
- H3 left OFF (no decision-level EV evidence; 12 Nov overbetdef lost 0.69).

## Changes
- **cand_b1** (sources `candidates/b1_src/`): (a) F-fold: FOLD_MIN_N 20->8, FOLD_N0 40->12, read from a window of the last 20 answers,
  only when fold rate >= 0.6 (switches off as the window turns); (b) `overfolder` move on; (c) new `foldall` move (H2): when overfolder
  says yes AND >= 90% folds in the last 24 flop/turn answers (>= 16 seen): check->small bet (share 0.6*strength), preflop fold->call vs raise (0.5*strength);
  guard TV cap 0.3 per decision applies; off when the window turns.
- **cand_b1b** (`candidates/b1b_src/`): (b)+(c) only, F-fold change reverted.
- Mechanism (s1_ranges, 6 legs): foldall_bet 107-133, foldall_defend 18-29, overfolder 17-25 decisions per leg; 0 hook errors, 0 over 5 ms.
  Bluff success on added river bets and firing counts vs the other bots were NOT measured (no per-move logging).

## Results (chips/hand, paired by seed, first-seed 100, 200-hand legs; SE from per-pair differences; base-vs-base noise floor about +-0.4 at 16 pairs per NB1)
cand_b1 (F-fold + overfolder + foldall) minus base:
| bot | base | cand | delta |
|---|---|---|---|
| eqtag (24) | +1.15 | +0.44 | -0.71 +- 0.31 |
| trapper (24) | +1.03 | -0.17 | -1.19 +- 0.37 |
| s1_ranges (24) | +3.54 | +4.40 | +0.86 +- 0.10 |
| s2_rollout (24) | +0.73 | +1.00 | +0.27 +- 0.40 |
| s3_exploit (24) | +1.16 | +0.81 | -0.34 +- 0.29 |
| **pooled dev** | | | **-0.22 +- 0.14** |
| holdout potctl / polar / s4_balanced (16) | | | -0.01 +- 0.34 / -0.30 +- 0.42 / -0.89 +- 0.39 (pooled -0.40 +- 0.22) |
Other 12 holdout bots, old pool, lakshya1: base done, cand_b1 NOT run (stopped once dev pooled was negative).

cand_b1b (overfolder + foldall only) minus base:
| bot | delta |
|---|---|
| eqtag (24) | -0.03 +- 0.33 |
| trapper (24) | -0.50 +- 0.33 |
| s1_ranges (24) | +0.89 +- 0.09 |
| s2_rollout, s3_exploit | not run |
| pooled (3 dev bots) | +0.12 +- 0.16 |
| holdout polar / s4_balanced (16) | +0.27 +- 0.53 / -0.73 +- 0.34 (pooled -0.23 +- 0.32) |
Head-to-head cand_b1b (A) vs base, 16 pairs: -0.08 +- 0.22, score 0.438. No forfeits or illegal replies anywhere (all runs). Time: no hook over 5 ms in the checked legs; full timing check not run.

## PASS rule (PLAYBOOK)
- cand_b1: dev pooled DOWN -> FAIL. eqtag and trapper drop 2.2 and 3.3 SE; the earlier F-fold is the likely cause (foldall cannot fire on these bots: their overfolder trait is "no").
- cand_b1b: dev "improved" only through s1_ranges (+0.89, 9 SE; an extreme never-calls bot); holdout pooled < 0 and s4_balanced down 2.2 SE (this bot should not trigger foldall, so most of that is likely noise, but the rule is the rule); head-to-head not better. -> FAIL / not shippable.

## Phil Ivey test
- Earlier river F-fold (H1): "If he folds the river 70% I bluff more, but ten hands is a story, not a read." Cutting the sample from 20 to 8 traded principle for noise, and the numbers say it lost. Verdict OVERFIT/premature: revert.
- foldall (H2): "A guy who never calls a bet: I bet every street and call his raises preflop; the moment he calls once, I stop." Clean principle with a switch-off, +0.9 chips/hand against the only bot that shows it. SITUATIONAL: correct, but it fires only against an extreme bot and gives nothing measurable elsewhere. Keep behind the gate; no evidence it matters against real submissions.

## Recommendation
No change passes. Keep `final` as is. For insurance against a never-calls bot, `cand_b1b` (foldall) is the low-risk candidate: deltas where it should be off are inside noise, +0.89 on s1_ranges. It needs the full guard set (12 holdout, old pool, lakshya1) before promotion.
Revert: the F-fold threshold change (cand_b1 only). H3 untouched.

## Not run
cand_b1 on 12 holdout bots, old pool (9) and lakshya1; cand_b1b on s2, s3, 13 holdout bots, old pool, lakshya1; head-to-head for cand_b1; per-move firing counts on non-s1 bots; seeded builds; 500-hand legs; full timing/memory benchmark. A container loss mid-run cut the plan.
