# MW handoff: match-win layer — NO-GO, DROP (nothing changed in `bot/`)

Branch `claude/mw-360090` = `tier4/mw`. Machine: shared laptop, 1 process. No `bot/` change, so no timing run, no suite run.

## Headroom measurement (stop rule applied)
Data: S0 recordings `logs/records/s0_9000` (tier3, locks off, 12 pairs = 24 matches x 400 hands per bot, seeds 9000-9011),
`d_new_rules` excluded and not analysed; held-out/blind2 never touched. Script: `python -m lab.opps.matchwin_headroom DIR`.
"Open" = |lead| < 1 SD of the remaining hands, SD = this match's per-hand SD x sqrt(hands left). "Flip" = sign of lead at
hand k differs from the final sign.

| bot (24 matches) | SD/hand | open@200 | open@300 | open@350 | flip@300 | flip@350 |
|---|---|---|---|---|---|---|
| d_conv_opp3 | 37 | 0.50 | 0.42 | 0.12 | 0.25 | 0.12 |
| d_new_exploiter | 32 | 0.54 | 0.21 | 0.08 | 0.00 | 0.04 |
| d_new_lag | 87 | 0.42 | 0.25 | 0.17 | 0.17 | 0.04 |
| d_new_minraise | 37 | 0.50 | 0.29 | 0.08 | 0.00 | 0.00 |
| d_new_trapper | 45 | 0.67 | 0.42 | 0.29 | 0.17 | 0.08 |
| tight | 47 | 0.29 | 0 | 0 | 0 | 0 |
| starter, calling_station, maniac, random_legal, all_in | 54-130 | 0 | 0 | 0 | 0 | 0 |
| all 11 bots | | 0.27 | 0.14 | 0.07 | 0.05 | 0.03 |

The simple bots are decided by hand 200 (we win by a wide margin; nothing to gain, the lock already covers the end).
Only the 5 strong d_* bots stay open: about 28 % at hand 300, 13 % at hand 350, flips 0-25 %.

## Upper bound on the gain (free of EV cost)
Model: after hand k, scale each match's remaining-hand deviation from its mean by s = 1 + min(|z|,1)(s_ahead-1) when ahead
(s_behind when behind), keep the mean. This is the best a perfect variance dial could do (no EV cost, no noise in the dial).
Strong bots, 120 matches, baseline score 0.542:
- k=300, ahead 0.7 / behind 1.3: **+0.008**; ahead 0.5 / behind 1.5: +0.008
- k=200, ahead 0.5 / behind 1.5: +0.017; milder scales: +0.000

So the ceiling is about +0.01 to +0.02 match score against the strong bots and 0 against the simple ones. Poker cannot be
scaled freely (a marginal bluff skipped also gives up EV; chips/hand guard of -0.3 would eat the gain), so the real gain is
a fraction of that. A 100-pair confirmation resolves a score difference of about 0.04 per bot (SE ~0.02 pooled), so
the effect would be undetectable, and an unmeasurable change on the shipped bot is risk without evidence.

## Decision
**NO-GO. DROP.** No `bot/strategy/matchwin.py`, no hook in `bot/situation.py`; the endgame lock stays the only match-state logic.
The 30-pair fresh run from the plan was not run: the bound above is far below detectability, so more data cannot flip the call.
Caveats: the model scales realized deviations (so it assumes the dial acts on all remaining hands equally), and 24 matches
per bot is small; neither can move a ceiling this far under the noise. Stage 2 (1000 hands) has the same shape in z terms.
Commit: see `git log` on `tier4/mw` (docs + the analysis script only).
