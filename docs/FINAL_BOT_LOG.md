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
