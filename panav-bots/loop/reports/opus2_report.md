# OPUS2 report: Stage 2 tactic = risk-capped match lock (15 Nov 2026)

**Verdict: ship stage2 lock.** It FAILS pre-registered rule 2 (raw chips >= 0) by design. It passes every match-win rule by a wide
margin, and the chips cost falls only on the tie-break. The owner/parent makes the final call; the numbers are below.
Normal build: `panav-bots/submission/bot_stage2.py`, identical to `panav-bots/loop/cands/sub_s2_lock.py`,
**sha256 5855fc7a8282b8a1971eb4205737a246c6571435334b6ddb136fa4967458fd85** (737 KB; CONFIG has no sample_seed/force_mode/solver_passes/slowdown;
the only change from A is `botsrc.main`, diff in `panav-bots/loop/opus2/lock_main.diff`, plus config `s2_lock: on`).

## What it is (research basis: opus2_research.md §1 safe exploitation, §5 match objective, §6 protocol fact)
docs/rules/protocol.pdf §5.1: `init.total_hands` = match length (400 / ~1000), one process per match, both duplicate seats inside it.
So the bot sees its match score. Armed only if total_hands >= 800 (Stage 2). Once net > 2 x hands_left, the bot plays A's decision
unless it would put more chips into the hand than R = net - 2(left-1) - 1; then it takes the cheapest of call/check/fold that fits.
After that the match cannot be lost. No tuned parameters. Phil Ivey: protect a lead that cannot be caught. Verdict: PRINCIPLE.

## MATCH WINS (Stage 2 length: 1000-hand single-process matches, split duplicate order, seeds 61000-61023, validation bots only)
Primary estimator (pre-registered): exact post-hoc replay on A's own trajectories (cand = A until the lock fires; after that it is a guaranteed win).
**Pooled, 15 bots, 360 matches: A 220/360 (61.1%) -> lock 263/360 (73.1%) = +11.9 ± 1.7 pp.** No bot goes down (it cannot, by construction).
| bot | A wins | lock wins | d pp ± SE | A chips/h | A capped/h |
|---|---|---|---|---|---|
| conv_opp3 | 17/24 | 19/24 | +8.3 ± 5.8 | +0.52 | +0.34 |
| eqtag | 17/24 | 21/24 | +16.7 ± 7.8 | +0.58 | +0.35 |
| lakshya1 | 11/24 | 16/24 | +20.8 ± 8.5 | -0.24 | -0.13 |
| new_eqrandom | 11/24 | 12/24 | +4.2 ± 4.2 | -0.23 | -0.08 |
| new_exploiter | 10/24 | 11/24 | +4.2 ± 4.2 | -0.33 | -0.23 |
| new_geometric | 12/24 | 15/24 | +12.5 ± 6.9 | +0.22 | +0.08 |
| new_trapper | 12/24 | 15/24 | +12.5 ± 6.9 | -0.00 | +0.03 |
| polar | 21/24 | 21/24 | +0.0 | +0.89 | +0.58 |
| potctl | 18/24 | 19/24 | +4.2 ± 4.2 | +0.67 | +0.48 |
| s2_rollout | 19/24 | 21/24 | +8.3 ± 5.8 | +0.76 | +0.48 |
| s3_exploit | 19/24 | 22/24 | +12.5 ± 6.9 | +0.55 | +0.38 |
| s4_balanced | 13/24 | 20/24 | +29.2 ± 9.5 | +0.11 | +0.06 |
| s5_preflop | 15/24 | 17/24 | +8.3 ± 5.8 | +0.07 | +0.11 |
| s7_solver | 17/24 | 20/24 | +12.5 ± 6.9 | +0.48 | +0.33 |
| trapper | 8/24 | 14/24 | +25.0 ± 9.0 | -0.45 | -0.29 |
(s10_regret: queue was stopped before it ran. That leaves 15 of the 16 pre-registered bots.)
Sensitivity: if the real engine puts duplicate pairs next to each other (`adjacent` order, post-hoc on permuted deltas, approximation): +6.1 ± 1.3 pp.

**Real lock build vs A, same seeds (pre-registered confirmation arm, 6 bots, 144 matches): +9.7 ± 5.2 pp** (lakshya1 11->14, new_eqrandom 11->13,
new_trapper 12->13, s7_solver 17->22, conv_opp3 17->17, eqtag 17->20). The sign agrees with the primary estimate.
**Head-to-head lock vs A, 40 matches (seeds 62000-62039): lock wins 30/40 = 75.0%**, chips -0.08 ± 0.08/hand.
Design bots (s6_discard, conv_opp4, new_minraise, seeds 60000-60015, implementation checks only): +10.4 ± 4.5 pp.

## Chips (stated plainly)
Real arm, pooled 6 bots: **raw chips -0.365 ± 0.095 /hand; capped chips (official tie-break, clip ±1000 per match) -0.248 ± 0.068 /hand.**
Cause: after locking, the bot mostly gives up blinds and edge for the rest of the match (~300 hands on average). This only affects the tie-break
among bots level on match points. It buys about +12 pp match wins, i.e. about +3.7 points over a 31-match round robin.

## PASS/FAIL against the pre-registered rule (opus2_prereg.md)
1. Pooled match wins >= +2.0 pp: **PASS** (+11.9 ± 1.7 primary; +9.7 ± 5.2 real).
2. Pooled chips >= 0: **FAIL** (-0.37 raw / -0.25 capped per hand). The pre-registration predicted this failure before the runs.
3. No bot down > 2 SE: **PASS** (none down in the primary; in the real arm the worst is conv_opp3 at 0.0).
4. lakshya1 not lower: **PASS** (11 -> 16 primary, 11 -> 14 real); h2h >= 50%: **PASS** (75%).
5. Safety: fuzz 0 illegal / 0 forfeits at total_hands 400 and 1000 (6 opponents each, `results/opus2/safety/fuzz_L.txt`): PASS. Static scan
   identical to A: PASS. Size 737 KB: PASS. 60-hand real-protocol run with python 3.11.18 vs starter bot at total 1000: 0 illegal, 0 forfeits,
   RSS 106 MB: PASS. No forfeits in any of the 1000-hand matches; worst reply in the validation runs 0.50 s; min bank left 68.6 s of 150.
   Stage 1 identity: replayed 400-hand input streams give byte-identical output to one of A's own outputs (A itself is not deterministic):
   PASS. 2x-slowdown timing (1000-hand match vs lakshya1, both seats): lock mean 24.4 ms / p99 128 ms / worst 0.32 s; A mean 24.4 / p99 128 /
   worst 0.27 s; bank used at most 86.6 s of 150 (58%) vs A 82.3 s (55%); RSS 130 MB vs 127 MB: PASS (worst < 1.5 s, same mean and p99).
   Lock legality: replay checker found 0 budget violations (`opus2/lockcheck.py`). The 2 flagged cases were desync artifacts, after we had folded.
**Overall by the letter: FAIL (rule 2 only).** Recommendation: ship stage2 lock for Stage 2; it does nothing at Stage 1 (total_hands < 800).

## Other findings
- In one-process 1000-hand matches A wins only 3/16 vs new_minraise (design) and 8/24 vs trapper. Worth knowing; not addressed here.
- Not pursued, with reasons in opus2_research.md: phase schedules on Bayesian trait intervals, Exp3 over styles (payoff noise 40 chips/hand),
  deeper solving (the time manager already gives the river solver up to a 67% bank plan).
