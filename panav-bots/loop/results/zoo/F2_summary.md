# F2 zoo map: final (A) vs each F2 bot

24 pairs x 200 hands, seeds 300.. (+500-hand legs, 8 pairs, seeds 400.. where chips/hand < +0.5). chips/hand are final's. SE as printed by file_duel.

| bot | chips/hand ± SE | match score | 500-hand legs c/h | final showdown win rate when opp bet |
|---|---|---|---|---|
| trapper | +0.75 ± 0.29 | 0.583 | - | 0.56 |
| potctl | +0.11 ± 0.30 | 0.500 | +0.13±0.34 | 0.66 |
| s2_rollout | +0.59 ± 0.24 | 0.583 | - | 0.65 |
| s6_discard | +0.47 ± 0.32 | 0.583 | -0.08±0.35 | 0.59 |
| new_trapper | +0.87 ± 0.26 | 0.646 | - | 0.37 |
| conv_opp4 | +0.89 ± 0.26 | 0.667 | - | 0.67 |
| new_minraise | +0.22 ± 0.28 | 0.521 | +0.11±0.23 | 0.56 |

Mean over the 7 bots: +0.56 chips/hand. No forfeits in any run (0/0). No bot needed the 12-pair cut (every 24-pair batch finished in well under 10 min).

Final is ahead on chips/hand at 200 hands against all 7 bots (none below 0); only s6_discard at 500 hands is slightly negative (noise). Weakest: potctl (+0.11 ± 0.30), new_minraise (+0.22 ± 0.28 at 200h, +0.11 at 500h), s6_discard (+0.47 at 200h, -0.08 ± 0.35 at 500h, 8 pairs = noise). Per-bot leak reports and traits are in the <bot>.txt files in this folder.

Per-bot leak notes (largest chips by ending are in each file): see files; no leak diagnosed here (measurement only).
