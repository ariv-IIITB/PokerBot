# ZOO MAP + cross-validated recursion (12 Nov; replaces "B3/B4 held out" in PLAYBOOK item 4 of Overfit protocol v2)

Owner: "run against ALL the bots, see where chips leak, fix recursively, make sure places where we frequently lose get fixed".
All bots are used for diagnosis, but in 4 FOLDS (families kept together; spar_v4/<x> goes with spar/<x>):
- F1: spar/eqtag, spar/polar, strong/s1_ranges, strong/s5_preflop, Opps/discard/new_lag, Opps/discard/conv_opp3, opponents/lakshya1.py
- F2: spar/trapper, spar/potctl, strong/s2_rollout, strong/s6_discard, Opps/discard/new_trapper, Opps/discard/conv_opp4, Opps/discard/new_minraise
- F3: spar/betfold, spar/light3b, spar/tilt, strong/s3_exploit, strong/s7_solver, strong/s9_sizing, Opps/discard/new_rules, Opps/discard/new_geometric
- F4: spar/donk, spar/adapt, spar/discardread, strong/s4_balanced, strong/s8_meta, strong/s10_regret, Opps/discard/new_exploiter, Opps/discard/new_eqrandom
Paths: `panav-bots/eval_bots/{spar,strong}/<name>/bot.py`, `Opps/discard/<name>/bot.py`, `panav-bots/opponents/lakshya1.py`.

## Rotation rule (this is the anti-overfit guarantee)
A round DESIGNS fixes from the leak maps of three folds and VALIDATES on the fourth (never looked at by the designer: no logs, no reports, only the final paired numbers).
Round 1 validates on F4, round 2 on F3, round 3 on F2, round 4 on F1 (accepted moves from earlier rounds stay in; each new candidate is re-run on all earlier validation folds, regression ledger).
Frequency rule: rank leaks by (chips lost, summed over bots) x (breadth = number of bots where it loses) x (seen in >= 2 families). Fix the highest first; stop at the first one that fails validation and go back to the ranking.
Final unbiased test: a set of NEW bots written late by separate sessions that no designer ever sees (to be created at the end); until then every number is cross-validated, not final.

## Zoo map (one session per fold; measurement only, no bot edits)
For each bot in the fold: final vs bot, 24 pairs x 200 hands (`--seeds 24 --first-seed 300`, logs on), `leak_report`; if final's chips/hand < +0.5 also 8 pairs x 500 hands (Stage 2 length, `--first-seed 400`).
Write `panav-bots/loop/results/zoo/<bot>.txt` (headline +-SE, match score, leak_report text, and a 5-line trait summary: first-in bet rate / fold-to-our-bet by street, raise rate, showdown win rate when it bets) and `results/zoo/F<k>_summary.md` (table, <= 40 lines).
