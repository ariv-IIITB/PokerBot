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
