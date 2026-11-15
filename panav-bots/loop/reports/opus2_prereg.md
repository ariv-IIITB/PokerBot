# OPUS2 pre-registration (written 15 Nov ~15:00 UTC, BEFORE any validation run; only design runs on s6_discard, conv_opp4, new_minraise exist)

## Fact this rests on (docs/rules/protocol.pdf §5.1, §3)
`init.total_hands` = "number of hands in the match (400 in Stage 1, about 1000 in Stage 2)"; the bot keeps no state between matches and
"is not told which deals are duplicates". So a real Stage 2 match is ONE bot process for ~1000 hands with both seats of every deal inside it,
and the sum of `hand_result.net` is the match score the bot is judged on. The lab's 2 x 500-hand-legs-in-two-processes setup hides this.
Harness used here: `panav-bots/loop/opus2/duel1000.py` (one process per bot for the whole match; `--order split`: deals 0..499 then the same
deals with seats swapped). Bank 150 s / 1000 hands, 5 s reply cap (forfeit), real `pokerbots` protocol.

## Tactic T1 under test: risk-capped match lock (`panav-bots/loop/cands/sub_s2_lock.py`, config `s2_lock: on`)
Armed only if `total_hands >= 800` (Stage 2). At each new hand, with net = match chips so far and left = hands not finished (this one
included): locked iff net > 2 x left. While locked, the bot plays A's decision unless it would put more than R = net - 2 x (left - 1) - 1 chips
into this hand; then the cheapest legal of call / check / fold that fits. Invariant: a locked hand loses <= R, so the next hand is locked again,
and the final net >= 1: the match cannot be lost once locked. No parameters were tuned (2 = the big blind, the most a check/fold hand loses).
Phil Ivey test: a pro protecting a lead that cannot be caught stops gambling; it uses only his own score and the hands left (fully observable,
not exploitable: the opponent cannot win back more than the blinds). Verdict PRINCIPLE.

## Estimators (fixed now)
- PRIMARY (match wins): exact post-hoc replay on A's own 1000-hand trajectories (`opus2/lockpost.py`). Before the lock the build runs A's
  code; once locked it cannot lose, so per match cand_score = 1 if the lock fires on A's trajectory, else A's score. This is a noise-free pairing
  (independent re-runs of A differ through wall-clock solver noise; this does not).
- CONFIRMATION (real build): cand and A on the same seeds on 6 of the validation bots (lakshya1, new_eqrandom, new_trapper, s7_solver,
  conv_opp3, eqtag), 24 matches each; must agree in sign with the primary (pooled cand - A wins >= 0 pp) and give the real chips.
## Bots, seeds
- Design (implementation checks only): s6_discard, conv_opp4, new_minraise; seeds 60000-60015.
- Validation (16 bots, never used for design): lakshya1, new_eqrandom, conv_opp3, eqtag, potctl, polar, new_geometric, new_exploiter,
  s7_solver, s4_balanced, s2_rollout, s3_exploit, new_trapper, trapper, s5_preflop, s10_regret. A: 24 matches each, seeds 61000-61023
  (single use). Confirmation arm: the same seeds. Head-to-head cand vs A: 40 matches, seeds 62000-62039.
- Ledger: 59000-59100 identity/smoke tests; 60000-60015 design; 61000-61023 validation; 62000-62039 h2h; 63000+ timing/fuzz.

## PASS rule (the brief's, unchanged; judged at Stage 2 length only)
1. Pooled MATCH WINS cand - A >= +2.0 pp over the 16 validation bots (primary estimator), with SE.
2. Pooled chips/hand cand - A >= 0 (real confirmation arm; raw chips as in the brief).
3. No validation bot's match-win rate down by > 2 SE (primary and confirmation arm).
4. lakshya1 match wins not lower than A; head-to-head cand vs A >= 50% of matches (real run).
5. Safety: legality fuzz (lab.fuzz WeirdPlayer kinds + starter bot) 0 illegal / 0 forfeits at total_hands 400 and 1000; reply time under the
   2x slowdown emulation not worse than A, worst < 1.5 s; bank use at 2x slow within 150 s / 1000 hands with margin; RSS < 1 GB; static scan
   clean; single file < 5 MB; 60-hand real-protocol `python3.11 bot.py` run clean; Stage 1 (total_hands < 800) behaviour identical to A
   (replayed input streams give output identical to one of A's own outputs).
Secondary, reported but NOT part of PASS: capped chips/hand (official tie-break: per match clip(net, -1000, 1000) / hands), and the lock
gain under the `adjacent` duplicate order (post-hoc on permuted deltas; approximation).
Expected risk, stated before the runs: rule 2 may fail by construction (locked hands give up blinds and edge); if so the verdict is FAIL on
rule 2 and the report says so, with the tie-break-aware number for the parent's decision. The rule will not be relaxed.
