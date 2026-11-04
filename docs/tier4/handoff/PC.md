# Handoff PC (selection, bail-out, stop-loss, adversary)
**Branch** `claude/subplan-xx-execution-4m4kgt` (not `tier4/p-sel`: assigned by the session), built on PA's branch
`claude/tier4-pa-subplan-cwh07j` @ 423503e (`origin/tier4/p` does not exist). `tier4p.py` untouched; `bot/cfr/` untouched.
**Machine:** 4 vCPU, Xeon 2.80GHz, `--processes 3`. Fast suite: 1347 passed, 2 skipped.
## Rules as built (`bot/brains/tier4p_select.py`, state in `brain._sel`)
- **Selection:** at our first decision of each hand; member kept for the hand. F = top X2 family; overfolder -> anti_folder;
  valueonly, trapper -> anti_value; aggressor -> anti_aggro; unknown/nit/station -> base. Needs mass(F) >= 0.8 at each of our
  last 20 decisions (same F every time, history updated on every non-locked decision), plus: anti_folder: X1 over-folder
  SPRT = "yes"; anti_value/anti_aggro: types.n >= 60. Else base.
- **Bail-out:** a new over-folder CUSUM alarm -> base at once (even mid-hand) and anti_folder blocked for 50 completed
  hands. Other members are not blocked by it.
- **Stop-loss:** checked once at the first hand start with hands_played >= 25/50/75 % of `match.hands`. Chips since the current
  non-base member switched on < -2 x SD x sqrt(n) -> base for the rest of the match. SD = per-hand SD of this match
  (>= 10 samples; hands without a decision of ours are folded into multi-hand blocks). **Deviation:** if a lock decision
  occurred since the switch the stop-loss is skipped (locked hands can't be isolated; a lock means the match is won).
- Any error -> base (`p_errors`). New stats: `sel_switches`, `sel_bailouts`, `sel_stoploss`.
- **Adversary** `lab/sparring/adversary.py`, registered in `lab/players.py` (outside the P file list; one line each):
  `adversary` (spec: folds to a postflop bet without a pair+, hands_played < 100; then a calling station) and
  `adversary_strict` (my addition: continues only with two pair+).
## Tests (`tests/test_tier4p_select.py`, 28)
Each family -> its member; 20-decision window (incl. mixed families); SPRT-yes and 60-obs conditions; one member per hand;
CUSUM block lasts exactly 50 hands; stop-loss only at checkpoints, only on a >2 SE loss, off after a lock; errors -> base;
locked decisions never reach selection; adversary switches at hand 100; registered and plays a legal match.
## Smoke runs (8 pairs, discard_holdem, seeds 8200-8207, locks off, not gates; logs in `logs/pc/`)
| opponent | chips/hand | score | member shares / events |
|---|---|---|---|
| d_new_exploiter | -1.31 ± 0.53 | 0.31 | anti_folder 5435 of 6411 hands (85 %), 18 switches, stop-loss fired in 2 of 16 matches |
| adversary | +19.80 ± 0.79 | 1.00 | base 100 % (its fold rate ~45 % is read as not-an-over-folder; X2: station/unknown) |
| adversary_strict | +16.81 ± 0.53 | 1.00 | base 100 %; X1 SPRT "yes" by hand ~25 and CUSUM alarm after hand 100 in 16/16 matches (`sel_bailouts=16`) |
PA's forced anti_folder vs the exploiter was -0.14 (other seeds): not comparable; PD should check auto vs forced.
## Timing (one ratio check, 400 hands, bank 60, maniac, seed 0, discard_holdem)
tier3 11.73 s used (39 % at x2); tier4p 12.31 s (41 %). Ratio 1.05 <= 1.4. `tests/test_timing_slow.py` not re-run (asked for one ratio check).
## For PD
- Findings: (1) out-of-library over-folders (the adversaries) land in X2 "unknown", so anti_folder is never chosen against them;
  the bail-out path was exercised only up to the alarm, not as an on-then-off switch. Library bots (exploiter) do select it.
  (2) Seed block: PC had none; 8200-8207 used.
- Merge: no conflicts expected with PB (`tier4p.py` values only).
