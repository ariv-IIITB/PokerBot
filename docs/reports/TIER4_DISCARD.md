# Tier 4 DA: smart rollouts on Tier 3 + retune (Discard Hold'em)

**Verdict: KEEP.** `bot/config/tier3.json` now sets `smart_rollout_discard: true` and `raise_equity: [0.70, 0.68, 0.68, 0.74]`
(`call_margin` stays 0.02). Machine: 14 cores, Intel Core Ultra 5 225H, shared with 3-4 other sessions (load average 25-30 during the
tuning; every eval ran under `nice -n 15`, 3-6 processes). Logs, driver and the raw tables are in `logs/da/`.

## Setup
Brain `tier3:{"smart_rollout_discard":true, ...}`, `--pool train tier1 tier2` (6 training bots + tier1 + tier2), `--variant discard_holdem`,
locks off, 400 hands, 30 pairs per point on seeds 53000-53029 (tuning), chips summed over the 8 bots. The difference to the current best is
the sum over bots of the chips/hand difference; its SE is the root of the summed squares of the per-bot SEs (as `lab.eval --compare`). A move
needs a gain > 1 SE. Driver: `logs/da/driver.py` (resumable); every move is in `logs/da/moves_dedup.log`.

## Cost (task 1)
`logs/da/timing.txt`: smart on vs off, 400 hands, 3 opponents x 2 reps, locked: bank used 48.49 s vs 46.79 s = **ratio 1.036** (limit 1.4).
Final check (`logs/da/timing_final.txt`): new shipped tier3 vs old tier3 (smart off, old thresholds), same protocol:
43.01 s vs 43.77 s = **ratio 0.98**; worst decision 20-52 ms. No "hard deadline" warning in either file (the timing harness may not show the bot's stderr).

## Tuning (30 pairs per point, seeds 53000-53029)
- Plain tier3 vs smart-on at Tier 3's values: **+0.72 ± 1.26** (no retune; noise).
- Round 1 (start `re 70-68-70-74, cm 0.02`): 
  `re[0]` 68: +0.33, 72: -0.27 | `re[1]` 66: +0.44, 70: -0.37 | `re[2]` 68: **+1.47 ± 1.24**, 72: +0.75 | `re[3]` 72: +0.37, 76: +1.33 ± 1.30 |
  `cm` 0.01: -0.47, 0.03: -0.37 (all ± 1.2). **Move: `re[2]` 0.70 -> 0.68** (+1.47 ± 1.24, z 1.2).
- Round 2 (around `70-68-68-74`): every neighbour is worse or equal: `re[0]` 68: -1.75, 72: -0.84 | `re[1]` 66: -1.06, 70: -1.22 | `re[2]` 66: -1.63,
  70: -1.47 | `re[3]` 72: -1.04, 76: +0.25 | `cm` 0.01: -1.41, 0.03: +0.83 (± 1.2). **Stop** (best +0.83 ± 1.25 is not > 1 SE).
  Rounds were capped at 3 by the manager; none was needed.
- 3 x 3 grid on the two most sensitive parameters (`re[0]` and `re[2]`, by the largest |change| in round 2), steps 0.02: all 8 neighbours worse
  (-0.84 ... -2.16, SE about 1.2). **Stay** at `70-68-68-74`, `cm 0.02`.
- Reading: with ± 1.2 per comparison nothing in the surface is distinguishable from noise except that the final point is the best of 14. The
  one move made (+1.2 SE) is a typical winner's-curse pick; that is what the fresh-seed confirmation is for.

## Confirmation (50 fresh pairs, seeds 54000-54049, new tier3 vs old plain tier3, same seeds)
Chips, locks off (`logs/da/confirm_chips.txt`): **sum +2.33 ± 0.88 (z +2.7)**. Per bot: conv_opp3 +0.44 ± 0.30, rules +0.38 ± 0.25, lag +0.96 ± 0.44
(improved), trapper +0.18 ± 0.23, exploiter +0.37 ± 0.25, minraise -0.02 ± 0.24, tier1 +0.20 ± 0.36, tier2 -0.18 ± 0.34. No bot down by > 2 SE.
Score, locks on (`lab/opps/score_compare.py`, `logs/da/confirm_score.txt`): mean 0.641 -> 0.648, **+0.006 ± 0.022 (z +0.3)** -> KEEP-score.
Two-part rule: **KEEP**. (50 pairs, one run, as the manager's light-testing rule asked.)

Not separated: how much of the +2.33 is smart rollouts alone and how much the `re[2]` 0.68 change (at the tuning seeds the
smart-on-default point was +0.72 ± 1.26 over plain and the final point +1.47 ± 1.24 over that). Both ship together.

## Deadline warnings in the tuning logs
`logs/da/deadline_hits.txt`: warnings "brain exceeded hard deadline" by point, mostly in loaded periods: the plain reference (smart off) had 185, the smart-on
start point 27, other points 1-344. They track machine load, not the flag. Confirmation logs: 0 / 0 / 0 (chips and plain score) and 7 in the smart-on
locks-on run. Decisions are not logged; per 1000 decisions the table assumes about 864k decisions per point (4.5 of ours per hand).
Unloaded and locked: none seen in `timing_final.txt`.

## Shipped change
`bot/config/tier3.json` (new) -> `bot/embedded.py` regenerated. `tier3x` and anything else with `param_file = "tier3"` reads the same file,
so they inherit these values. Tests: `tests/test_tier3.py` (the new values; the Tier 2 equality test now skips keys tier3.json sets).
Fast suite: 1291 passed, 2 skipped.

---

# Tier 4: discard (D stream)

DA writes its own section (rollouts + retune) on branch `tier4/d`; this file starts with DB's.

## DB: what their discard tells us

Data: S0's recordings `logs/records/s0_9000/` (seeds 9000-9011, 12 pairs = 9,600 hands per bot, brain `tier3`, locks off,
`discard_holdem`). Code: `lab/opps/discard_rules.py` (`python -m lab.opps.discard_rules`). Machine: 4 cores, Xeon @ 2.80GHz.
The recorder keeps `opp_hole3` on **every** hand, so the fit has no showdown bias: each row is every hand where the
opponent reached the discard.

### D0: rule fit

`hit` = the real drop is among the drops the rule accepts (ties give a set), `(set)` = mean set size. `random` accepts all
three drops, so its 100 % means nothing; the others should be read against their set size (about 1.05-1.15, so chance is ~35 %).
`disagree` = share of discards that differ from the drop `opponent_keeps` (our model) would make.
Rules: `opponent_keeps` = best 5-card hand with the flop, ties to higher ranks (deterministic, as in `bot/sim/discard.py`);
`drop_lowest`; `keep_pair` = keep a pair or better with the flop, else drop lowest; `keep_flush_draw` = keep two suited cards
with >= 2 flop cards of the suit, else drop lowest; `keep_straight_draw` = keep two cards in a 5-rank window with >= 4 of
the ranks of keep + flop, else drop lowest.

| bot | discards | disagree w/ opponent_keeps | opponent_keeps hit (set) | drop_lowest hit (set) | keep_pair hit (set) | keep_flush_draw hit (set) | keep_straight_draw hit (set) | random hit (set) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all_in | 3415 | 66.6% | 33.4% (1.00) | 35.7% (1.09) | 34.4% (1.05) | 35.7% (1.08) | 36.2% (1.09) | 100.0% (3.00) |
| calling_station | 9597 | 66.4% | 33.6% (1.00) | 36.9% (1.09) | 35.4% (1.05) | 36.9% (1.09) | 36.9% (1.10) | 100.0% (3.00) |
| d_conv_opp3 *(train)* | 5006 | 23.0% | 77.0% (1.00) | 61.6% (1.11) | 70.8% (1.05) | 63.7% (1.10) | 61.1% (1.11) | 100.0% (3.00) |
| d_new_exploiter *(train)* | 4894 | 21.5% | 78.5% (1.00) | 62.6% (1.09) | 72.7% (1.04) | 65.9% (1.08) | 65.1% (1.10) | 100.0% (3.00) |
| d_new_lag *(train)* | 6195 | 25.1% | 74.9% (1.00) | 59.7% (1.09) | 69.2% (1.04) | 61.8% (1.09) | 61.4% (1.10) | 100.0% (3.00) |
| d_new_minraise *(train)* | 6367 | 12.9% | 87.1% (1.00) | 68.1% (1.10) | 81.5% (1.05) | 70.1% (1.10) | 68.0% (1.11) | 100.0% (3.00) |
| d_new_rules *(train)* | 4860 | 20.8% | 79.2% (1.00) | 61.6% (1.10) | 72.1% (1.05) | 64.1% (1.10) | 61.7% (1.11) | 100.0% (3.00) |
| d_new_trapper *(train)* | 5580 | 17.3% | 82.7% (1.00) | 66.8% (1.09) | 77.3% (1.05) | 68.2% (1.09) | 65.9% (1.10) | 100.0% (3.00) |
| maniac | 6979 | 66.5% | 33.5% (1.00) | 36.8% (1.09) | 35.1% (1.05) | 36.6% (1.09) | 36.7% (1.10) | 100.0% (3.00) |
| random_legal | 2459 | 67.4% | 32.6% (1.00) | 34.4% (1.08) | 33.4% (1.04) | 33.8% (1.08) | 34.9% (1.09) | 100.0% (3.00) |
| starter | 9597 | 23.5% | 76.5% (1.00) | 100.0% (1.09) | 85.6% (1.05) | 95.6% (1.09) | 88.7% (1.10) | 100.0% (3.00) |
| tight | 3982 | 68.0% | 32.0% (1.00) | 38.6% (1.16) | 34.5% (1.06) | 38.1% (1.15) | 39.0% (1.16) | 100.0% (3.00) |

Go/no-go (training bots): **NO-GO**

- d_conv_opp3: disagree 23.0%, best other rule keep_pair 70.8% -> no
- d_new_rules: disagree 20.8%, best other rule keep_pair 72.1% -> no
- d_new_lag: disagree 25.1%, best other rule keep_pair 69.2% -> no
- d_new_trapper: disagree 17.3%, best other rule keep_pair 77.3% -> no
- d_new_exploiter: disagree 21.5%, best other rule keep_pair 72.7% -> no
- d_new_minraise: disagree 12.9%, best other rule keep_pair 81.5% -> no

**Reading.** The go test (a training bot disagrees with `opponent_keeps` on >= 15 % *and* one rule explains >= 80 % of its
discards) **fails for every training bot**: five of six disagree >= 15 % (minraise 12.9 %), but the best other rule
(`keep_pair`) explains only 69-82 %. Most of the time the training bots *do* play our `opponent_keeps` (75-87 %). What they
do differently is not one clean rule: on the hands where they disagree, `keep_straight_draw` explains 27-57 % and
`keep_flush_draw` 20-41 %, i.e. they sometimes keep a draw over a made pair. `opponent_keeps` plus `keep_straight_draw` together
reach 83-94 % (a two-rule mixture; not what the plan's test asks for). The sparring bot `starter` is the clean case:
`drop_lowest` explains 100 % of its 9,597 discards (it disagrees with `opponent_keeps` on 23.5 %), but `starter` is a
sparring bot, not a training bot. The other sparring bots
(`calling_station`, `all_in`, `maniac`, `random_legal`, `tight`) discard essentially at random (33-39 % hit).

**Decision: NO-GO for part 2** (learned keep rule). Part 2 is not built; `inference.py` is unchanged.

### D4: do they read our discard?

Their fold rate facing our bet on the turn (street 2), by the rank of the card we discarded (low 2-5, mid 6-T, high J-A);
chi-square 3x2, Holm across bots at 0.01. Caveat: our discarded card correlates with the strength of what we kept, so a
difference here would not by itself prove the bot reads the discard (a null is the cleaner result).

| bot | fold% low (n) | fold% mid (n) | fold% high (n) | chi2 p | Holm-adj (train) | Holm-adj (all) |
|---|---|---|---|---:|---:|---:|
| all_in | nan% (0) | nan% (0) | nan% (0) | - | - | - |
| calling_station | 0.0% (2156) | 0.0% (1875) | 0.0% (887) | - | - | - |
| d_conv_opp3 | 65.9% (744) | 69.0% (633) | 68.3% (341) | 0.427 | 1 | 1 |
| d_new_exploiter | 78.5% (530) | 78.6% (482) | 77.9% (217) | 0.975 | 1 | 1 |
| d_new_lag | 17.5% (749) | 21.2% (737) | 17.9% (429) | 0.16 | 0.64 | 1 |
| d_new_minraise | 38.1% (683) | 37.7% (549) | 29.3% (266) | 0.0305 | 0.153 | 0.244 |
| d_new_rules | 59.9% (464) | 52.9% (397) | 48.5% (202) | 0.0131 | 0.0788 | 0.118 |
| d_new_trapper | 23.7% (938) | 21.4% (765) | 23.3% (318) | 0.536 | 1 | 1 |
| maniac | 2.6% (1060) | 2.9% (919) | 2.2% (449) | 0.743 | - | 1 |
| random_legal | 43.4% (288) | 42.3% (281) | 43.1% (130) | 0.967 | - | 1 |
| starter | 0.0% (1795) | 0.0% (1601) | 0.0% (807) | - | - | - |
| tight | 31.4% (908) | 32.6% (706) | 28.9% (291) | 0.517 | - | 1 |

Bots that react to our discard (Holm-adjusted p < 0.01, all bots): none
Training bots only: none


**Reading.** No bot reacts (smallest p: `d_new_minraise` 0.031 raw, `d_new_rules` 0.013 raw; Holm-adjusted 0.15 / 0.08 for
the training set). Folding is flat across the three classes for the others. `starter`, `calling_station` never fold on the
turn and `all_in` never faces a turn decision, so they cannot be tested. The `hide_discard` A/B has no bot to be measured on:
DC should not spend a gate on it. The weak low-to-high trend for `d_new_rules` (59.9 % -> 48.5 %) and `d_new_minraise`
(38.1 % -> 29.3 %) is the only thing that could be followed up, with more seeds; it is not a result.

## DC: our discard on top of DA + DB (all levers DROP)

Setup, numbers and the timing caveat are in `docs/tier4/handoff/DC.md`. Summary: the 2-rule keep mix (`discard_mix`, `discard_eps`) passes the
likelihood gate on every bot but is flat in play (30 pairs, ± 1.2); the online keep-rule learner (`discard_learn`) is flat (-0.34 ± 1.22,
-0.08 ± 0.69); 1.5/8000 worlds -1.64 ± 1.18, 2.5/12000 (1.33x time) -0.02 ± 1.16. All stay default off, shipped config unchanged. DA's smart
rollouts cost 0.99x (corrected `lab.timing_bench`). Logs and drivers: `logs/dc/`.
Fast suite: 1312 passed, 2 skipped.
