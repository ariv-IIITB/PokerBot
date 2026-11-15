# OPUS1 pre-registration (written 15 Nov 2026 ~14:20 UTC, BEFORE any validation run; not to be changed after)

## Candidate
`panav-bots/loop/cands/sub_v2.py` = A (`cands/sub_disc_probe.py`) + **probe exit** (config `probe_exit: on`). Only `botsrc.exploit` and
CONFIG differ from A (all other modules byte-identical, checked with bundle_tool unpack + diff). Seeded twin: `opus1/evalbuilds/sub_v2_seeded.py`.
Mechanism: new trait `probeexit` = per opponent decision facing our TURN bet after it checked to us on the turn, x = fold. Wald SPRT
p0 0.28 / p1 0.48, alpha = beta = 0.10 (LLR per observation changes sign at f = 0.376 = break-even of a 0.6-pot bluff). Verdict "no" (folds
too little) => the probe move is off on every street (final's own lines) until the trait's CUSUM reopens it. Open / "yes" => A exactly.
Until the first "no" verdict in a leg, v2 makes exactly A's decisions (the trait only observes).

## Design data (seeds 46000-46023 and 46100-46101, design only) and what was looked at
Design bot: new_trapper (diagnosis + smoke). new_eqrandom: diagnosis only (no leak found in A, see report; nothing designed for it).
The SPRT constants come from break-even arithmetic, not from a fit. False-exit check: the test was replayed offline on META1's base logs of all
30 zoo bots (seeds 13000-13023, final's play) — that look is disclosed here; it fires in 0 % of legs for 24 bots, 2-10 % for
new_minraise / polar / new_geometric / new_lag, 73 % for new_trapper (92 % on A's own logs vs new_trapper). No constant was changed after it.

## Validation runs (fresh single-use seeds; all normal non-seeded builds; 3 processes; real protocol; file_duel copy `opus1/duel.py` with stderr kept)
- Stage 1, 200-hand legs, 40 pairs, seeds **50000-50039**, v2 vs bot and A vs bot, 20 bots:
  listed: new_trapper, spar/trapper, new_eqrandom, lakshya1, conv_opp3, spar/eqtag, spar/potctl, spar/polar, new_geometric, new_exploiter;
  +10 (not designed on): new_lag, new_minraise, new_rules, conv_opp4, strong/s2_rollout, strong/s5_preflop, strong/s7_solver,
  strong/s10_regret, spar/light3b, spar/tilt.
- Stage 2, 500-hand legs, 24 pairs, seeds **51000-51023**: lakshya1, new_eqrandom.
- Head-to-head v2 vs A, 200h, 40 pairs, seeds **52000-52039**.
- **Cost rule (fixed now):** v2 is always run. If v2's exit fired in 0 legs of a run (every leg's stderr exploit summary shows `probeexit` never
  "no"), v2 played A's code path in every decision of that run, so A is NOT re-run: the delta is 0 by construction and A's W/N is reported equal
  to v2's (marked "identical, gate never fired"). If it fired in >= 1 leg, A is run on the same seeds and the paired delta (by seed) is reported.

## PASS rule (all must hold)
Match = one duplicate pair, win if total chips > 0 (draw 0.5). Deltas are v2 - A, paired by seed, SE over seeds.
- **(a1) new_trapper (S1):** match-win delta > 0 AND chips/hand delta > 0 (point estimates; SE reported).
- **(a2) new_eqrandom (S1 and S2):** the diagnosis found no A leak to fix, so the requirement is "not worse": delta W >= -1 SE and delta chips
  >= -1 SE in each stage, and the exit fires in <= 5 % of its legs. (This replaces "improves" for new_eqrandom; decided before validation, with the
  reason in the report: a rule built for a non-reproducible deficit would be fitting noise.)
- **(b) other 18 bots (S1):** pooled match-win delta >= 0.0 pp; no single bot's match-win delta below -2 SE of its own paired delta;
  lakshya1 S1 and S2 match-win delta >= 0.
- **(c) h2h v2 vs A:** v2 wins >= 50 % of the 40 matches, or the shortfall is within 2 SE (SE = sqrt(p(1-p)/40) at p = 0.5, i.e. >= 34.2 %).
- **(d) speed:** mean reply time of v2 within 5 ms of A on the same timing run; worst reply < 1.5 s.
- **(e) safety:** legality fuzz (lab.fuzz.WeirdPlayer + starter bot) 0 illegal / 0 forfeits at init total_hands 400 and 1000; 2x slowdown
  timing no worse than A (bank use within 2 percentage points); RSS < 1 GB; static scan clean (stdlib + numpy); single file < 5 MB;
  a 60-hand real-protocol `python3.11 bot.py` run clean; no eval-only keys in the shipped CONFIG.
Decision: all pass => ship v2 (`panav-bots/submission/bot_v2.py`, sha256 in the report). Any fail => recommend A (or neither fix) as the
numbers say; the rule is not relaxed after the results.
