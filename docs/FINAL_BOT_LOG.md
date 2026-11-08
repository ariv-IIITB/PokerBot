# Final bot log (from 2026-11-08; the plan and every result, newest last)

Goal (user, 2026-11-08): one final bot, tested thoroughly. Order: cut the bloat, add the v6 ideas and general
exploits behind flags, test the combinations (v6 is held-out: measure only), run I1's gates, package.
Branch `claude/cool-mayer-jkn1k0` (= `tier4/int` + this work). An hourly heartbeat continues the work.

## 2026-11-08
- Merged `origin/tier4/int` (the shipped `tier3x`). Fast suite 1363 passed.
- Added the user's friend's bot as `Opps/discard/v6` (`d_v6`, held-out).
- Organisers' engine (`starter_kit/engine.py`, real Discard Hold'em, packaged `tier3x` vs v6, 20 matches,
  seeds 41001-41020): **9-11, -3913 chips over 8000 hands = -0.49 +- 0.22 chips/hand**. Wins small, losses big.
- **Trap found: `lab.eval` defaulted to plain Hold'em** (`lab/opps/holdem_100bb.json`). In Hold'em Tier 3's
  own code is off (no 3-card tables), so tier3x plays as Tier 2. The Tier 4 sessions passed
  `--variant discard_holdem` via their scripts (checked: logs/rf, logs/da, logs/final, logs/h1), so their
  numbers stand. This session's first lab run vs v6 (-1.58/hand, "flop folds") and the first coverage run
  were Hold'em and are void. Default is now `discard_holdem`.
- Built `x_selfdef` (self-check) and `x_cr` (raise a frequent bettor that folds to our bets) in `tier3x`, both off;
  `tests/test_ideas_v6.py`. Both fire in Discard Hold'em (smoke: x_selfdef 29 vs lag, x_cr 35 vs v6, 0 errors).
- Combination test started on 4 cloud sessions (40 pairs, seeds 40100, locks off, 200h/30s; arms base, sd, cr,
  fast, sdcr, all, noovf, nosolver; driver `lab/combo_run.sh`, report `lab/combo_report.py`). Results land on
  branches `combo/g1`..`combo/g4` (g1: conv_opp3 exploiter tier1; g2: trapper lag calling_station;
  g3: minraise rules maniac; g4: tight random_legal starter). Held-out (conv_opp4 eqrandom geometric v6) untouched.
- Sessions: G1 session_014YAsY3homWiEMdQbvPvXn2, G2 session_014YAsY3jJZVmTyxJiZJuaRv,
  G3 session_014YAsY29pQUhXSF9J8GUL8L, G4 session_014YAsY4a7Cq5c1fhFAWy1sa.
- Coverage (12 opponents, Discard Hold'em, 2 pairs each): 65 % of bot/ runs. Decision code is mostly used
  (tier3 76 %, river solver 77 %). Never run: tier0 (safety fallback, kept), lab-only CFR abstraction (moved to
  lab/cfr/), other-variant steps and other wire formats (kept: lab toolkit, cheap in the package).
- Cut: x_stab and x_def code/params/tests (both off; dropped/reverted earlier). hide_discard kept as a test arm
  (v6 reads our discard; its old A/B was vs bots that do not).
- Repo: binary logs removed (logs 23 MB -> 4 MB, history keeps them); Tier 4 plans/manager files and old phase
  plans moved to docs/archive/; tools/tier4_monitor.py removed.

- I1 gates (tier3x, this machine): `lab.memory_check` peak RSS 42.4 MB (limit 1024); `lab.fuzz --subprocess`
  2,000 hands / 20 matches, 0 failures (967 illegal opponent replies handled).
- Combo G4 done (tight, random_legal, starter; 40 pairs, off, chips/hand vs base): every arm is within noise except
  nosolver: -18.33 +- 0.72 vs starter, -1.81 +- 0.64 vs random_legal. The river solver stays.
  G1 partial (conv_opp3) also all noise. A local hide_discard A/B (11 training bots, 40 pairs) is running here.

## State / next (for a fresh context)
- Waiting on cloud combo sessions G1-G4 (branches combo/g1..g4, ids above). When all four have pushed: fetch,
  copy logs/combo/off/* into one dir, run `.venv/bin/python -m lab.combo_report off`, pick the best stack
  (sum up, no bot down > 2 SE), then a locks-on score run of base vs best (40 pairs) and hide_discard as an arm.
- Then I1 gates on the pick: timing ratio vs tier3 (lab/rc_ratio.py, clock_scale 2), lab.memory_check,
  lab.fuzz --subprocess, head-to-head vs main's tier3 (100 pairs), Stage 2 (500h/75s), held-out --final once
  (d_conv_opp4 d_new_eqrandom d_new_geometric d_v6), organisers' engine vs v6 (20+ matches) and vs starter.
- Then package (`tools.package_submission --zip --stage2`; its x2 timing projection over-states the solver, known),
  sha256 into docs/SUBMISSIONS.md, update docs/STATUS.md.
- Hourly heartbeat: trigger trig_01KHWdDx8zvUqy4czGYDrwZo (minute 6).
