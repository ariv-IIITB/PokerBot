# DB handoff: what their discard tells us

Branch `claude/subplan-xx-5o7o4k` (from `origin/tier4/base` + `origin/tier4/s0` merged for the recordings). Sub-plan said
`tier4/d-learn`; this session was told to push the `claude/...` branch, so DC merges from there.
Machine: 4 cores, Intel Xeon @ 2.80GHz. No `bot/` change, so no timing run. Fast suite: 1302 passed, 2 skipped.

## Part 1 result: NO-GO for the learned keep rule (part 2 not built)
D0 on S0's recordings (seeds 9000-9011, 9,600 hands per bot, every hand with a discard, no showdown bias since `opp_hole3` is on all hands).
Share of discards that differ from `opponent_keeps` / best other rule's share:

| training bot | disagree | best other rule | explains |
|---|---:|---|---:|
| d_conv_opp3 | 23.0% | keep_pair | 70.8% |
| d_new_rules | 20.8% | keep_pair | 72.1% |
| d_new_lag | 25.1% | keep_pair | 69.2% |
| d_new_trapper | 17.3% | keep_pair | 77.3% |
| d_new_exploiter | 21.5% | keep_pair | 72.7% |
| d_new_minraise | 12.9% | keep_pair | 81.5% |

Go needs disagree >= 15 % **and** one rule >= 80 %: no training bot passes (minraise has the rule share but not the disagreement).
`opponent_keeps` itself explains 75-87 % of the training bots, so our model is mostly right. The disagreements are a **mix**
(they sometimes keep a draw over a made pair: `keep_straight_draw` explains 27-57 % of the disagreeing hands,
`opponent_keeps` + `keep_straight_draw` reach 83-94 %), not one rule. Sparring bot `starter` is a clean `drop_lowest` (100 % of
9,597 discards); the other sparring bots discard ~at random. The full table is in `docs/reports/TIER4_DISCARD.md`.
If you want to override the no-go: a 2-rule mixture (opponent_keeps + keep_straight_draw, with a per-type weight) is the only
thing the data supports, and it adds at most ~13 points of explained discards on the training bots. My call: not worth a gate.

## D4: do they read our discard? No bot does
Turn fold rate by rank of the card we discarded (low/mid/high), chi-square, Holm 0.01: **no bot reacts** (training-set
Holm-adjusted p: minraise 0.15, rules 0.08, others ~1; raw smallest 0.013). `starter`/`calling_station` never fold on the turn,
`all_in` never reaches it. So **DC should not run a `hide_discard` A/B**; no bot to measure it on.

## Files
`lab/opps/discard_rules.py` (rules, `fit_rules`, D4, `python -m lab.opps.discard_rules [--md OUT]`), `tests/test_discard_rules.py`
(6 tests), `docs/reports/TIER4_DISCARD.md` (new; DA appends its own section there: expect a trivial merge conflict at DC),
this note. `bot/sim/inference.py` untouched, no param added, no embed change, no seeds 21000+ used (offline only).

## DC needs
- Nothing from DB for `choose_discard`: keep `opponent_keeps` as the opponent model. No `discard_rule_model` param exists.
- Skip the `hide_discard` test (D4). The budget test (`special_budget_frac`) is unaffected.
