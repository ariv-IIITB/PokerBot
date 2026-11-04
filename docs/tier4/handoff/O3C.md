# O3C handoff (2026-11-05): arm A vs arm B on top of tier4/int, and the timing check
Branch tier4/o3c (= tier4/int 1a0e8a1 + logs/o3c). Machine: nproc 14, Intel Core Ultra 5 225H. Steps 1, 2, 4 (locks-on score, simple-bot guard,
blind d_new_rules) and the 3-bet study were done by the cloud session / are with it; not repeated here.

**Recommendation: keep arm B (the tier4/int default: x_narrow on, x_air_eq 0.45). Do not switch to A.**

**Step 3: locks off, 50 pairs, seeds 76000-76049, 5 bots (no d_new_rules, no held-out), one lab.eval per bot, --processes 3.**
Arms: base = `tier3x:{"x_narrow":false,"x_air_eq":0.0}` (verified: both flags off), A = `tier3x:{"x_air_eq":0.0}` (x_narrow only), B = `tier3x`.
chips/hand, diff vs base ± SE (z):
| bot | base | A | B |
| d_conv_opp3 | -1.66 | -0.60 (+1.06±.27, z +4.0) | -0.14 (+1.52±.25, z +6.1) |
| d_new_lag | +6.57 | +5.47 (-1.10±.44, z -2.5) | +5.87 (-0.70±.45, z -1.5) |
| d_new_trapper | +0.09 | +2.21 (+2.12±.21) | +2.33 (+2.24±.21) |
| d_new_exploiter | -0.85 | +0.02 (+0.87±.20) | +0.08 (+0.93±.19) |
| d_new_minraise | +0.62 | +1.01 (+0.39±.19) | +0.96 (+0.34±.20) |
| sum | | +3.34±0.62 (z +5.4): `--compare` DROP (lag z -2.5) | +4.33±0.62 (z +7.0): KEEP |
B vs A: sum +0.99±0.56 (z +1.8); conv_opp3 +0.46±.19 (z +2.4); lag +0.40±.44 (B loses less vs lag, not more); others within noise.
Why B: the extra gain (x_air_eq, the river bluff pool vs an over-folder) lands where intended (conv_opp3, +0.46), and A, not B, is the arm
that fails the keep rule on lag. B's lag loss (-0.70, z -1.5) stays inside 2 SE and lag is still +5.87/hand.
Logs: logs/o3c/s3_{base,A,B}_off.{json,txt}; per-bot parts in logs/o3c/parts76/ (s1_* there are an abandoned locks-on start, unused).

**Step 5: timing, `lab.timing_bench` with DC's fix (config via $POKERBOT_BRAIN_CONFIG, tool as merged in tier4/int 1a0e8a1), exclusive lock,
discard_holdem, 400 hands, seed 1, 2x slowdown, tier3 then tier3x back to back (logs/o3c/timing.txt):**
| opponent | tier3 | tier3x (B) | ratio |
| d_conv_opp3 | 5.04 s (17% of bank), 1369 decisions | 5.54 s (18%), 1444 | 1.10 |
| d_new_exploiter | 4.99 s (17%), 1350 | 5.25 s (17%), 1398 | 1.05 |
Ratio <= 1.4 limit: PASS. Mean decision 3.7 vs 3.8 ms, worst 20 ms in both. The bench output prints no hard-deadline hit count;
the tail of its output shows no forfeit or deadline line for either brain. Not run: tests/test_timing_slow.py, the fast suite.

**Not done / caveats:** one 50-pair sample per arm, one seed block (76000); the lag drop (-0.70 ± .45) is not zero, only below the 2 SE rule.
x_stab (arm C, earlier screening) stays dropped. Held-out bots never run; d_new_rules not run by this session.
Resume: `logs/o3c/run_o3c.sh` (queue) and `logs/o3c/run_timing.sh`.
