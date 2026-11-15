# DISC1: is final's discard leaking equity? (13 Nov 2026)  VERDICT: FAIL (pre-registered rule), mechanism real

## 1. How final discards
`botsrc.policy.decide_discard`: a blueprint table row `DISC[(b3, pot class, flop aggressor, seat)]` over 3 slots (keeps sorted by S1,
the one-card-lookahead equity). 444/500 sampled rows are pure (>97% on one slot), so there is no deliberate mixing (caveat b is moot).
The key (b3 = class of the best pair x gap to the 2nd) sees neither the 3rd pair nor suits/draws. Pure rows often pick a lower slot,
e.g. 6h6c2d on Jc4c8c (66 + flush draw, eq .52): row says keep 6h2d (eq .10), 42 points lost.

## 2. Offline audit (caveat a handled)  `tools/disc1_eval.py`, `disc1_report.py`; numbers in `reports/disc1_audit.txt`
final_seeded, seeds 9000-9029, 6 bots (trapper betfold donk light3b new_exploiter new_lag), 30 pairs x 200h, n = 27,656 discards.
Loss = equity of best keep - equity of chosen keep (cross-fitted halves, so no max-of-noise bias; points of equity):
| opponent model | loss per discard |
|---|---|
| random 2 cards (D1 target) | 1.19 +-0.03 |
| holds 3 random cards, keeps best by S1 (caveat a) | **1.02 +-0.02** |
| actual showdown hand (n=11,915, exact runouts) | 1.86 +-0.06 |
Handling (a) lowers the loss by only ~15%: **the loss is real**. By seat: button 1.09, BB 0.93. By pot at discard: 0.8-1.4 in every bin.
Flop betting: nobody bet 1.14, we bet 1.08, opp bet 0.89, both 1.27 (position/range info does not explain it).
By chosen type: high 5.8 (43% >= 3 pts), suited_conn_hi 3.8, board_pair 2.3, overcards 1.8, high+sd 1.5; made hands ~0.1-0.4.
Top mistakes: high->high 457, board_pair->board_pair 274, high->pair_other 162, high->pocket_pair 145.
When the blueprint deviates from the max-S1 keep (12% of discards) the max-S1 keep is better in 73% of cases (mean +5.6 pts).
Simple rules re-scored: keep max-S1: 0.28 +-0.01; follow blueprint only if its S1 within 0.02/0.04/0.08 of max: 0.30/0.32/0.33.
Choosing by equity vs random instead of vs the "best-of-3" model changes the loss by only 0.02 pts, so the cheap model is used.

## 3. Candidate (discard path only; config `disc_eq=on`, base = same file without it)
Keep the max-S1 pair; keeps within 0.12 of the max S1 (one-card scale) are compared by 1000-sample Monte Carlo equity vs a random
2-card hand over random turn+river; deterministic seed per deal. Falls back to the blueprint row on any error. Replaces the row
(exploit_adjust still applies). Offline loss 0.03-0.10 pts (betfold 800 discards: 0.03; smoke run 78 discards: 0.10).
Speed: 1.57 ms mean, 2.7 ms p95, 9.9 ms max per discard (box under load); limit was 5 ms mean. Added mean reply time
~ +0.3 ms over all replies (discards are ~1 in 5 replies). Files: `evalbuilds/final_disc_seeded.py` (cand), `final_seeded.py` (base).

## 4. Pre-registered check (seeds 9100-9139, 40 pairs x 200h per bot, paired by seed; `tools/disc1_run.sh`, `disc1_agg.py`)
18 bots (9 spar + 9 Opps/discard). Per bot table: `results/disc1/agg_final.txt`.
- POOLED delta cand-base: **+0.075 +-0.051 chips/hand** (720 pairs, ratio 1.48). Rule needed >= +0.10 AND >= 1.5 SE: **NOT MET**.
- Match wins pooled: base 0.635, cand 0.649 (not lower: met).
- Largest per-bot drop: new_exploiter -0.34 +-0.19 (-1.8 SE; rule "no bot down by > 2 SE": met). Best: conv_opp4 +0.39 +-0.15, conv_opp3 +0.33 +-0.18.
  Bots up / down: 9 / 9 (small, mostly within 1 SE each).
- Head-to-head cand vs base (40 pairs): +0.065 +-0.152 chips/hand, cand match wins 0.600 (>= 0: met).
- Stage 2 length, 500h legs, 24 pairs, seeds 9200+: lakshya1 delta -0.14 +-0.20 (base -0.08, cand -0.21; wins .54/.38);
  new_eqrandom delta +0.12 +-0.13. Both inside noise (interpretation fixed beforehand: "not worse" = delta >= -1 SE; lakshya1 is -0.7 SE: met, weakly).
- Forfeits/illegal replies: 0. Stage 1 (200h) and Stage 2 (500h) are reported separately above; the 500h sample is too small to say anything.

## 5. Ivey test
A great heads-up player keeps the two cards with the most equity against the opponent's likely range unless there is a concrete
reason (hiding a draw, keeping a blocker) and here the discard is revealed after the flop betting, so there is little to hide and
no reason to keep 6-2 over a pair of sixes with a flush draw. The blueprint's pure low-slot rows come from a coarse abstraction, not from
an equilibrium argument, so "keep the best equity" is the principle. It cannot be exploited back: the opponent already sees the
discard, and our rule is more honest than the table. Verdict: PRINCIPLE (mechanism), but the chip gain is small.

## 6. Verdict: FAIL on the pre-registered pooled rule (+0.075 < +0.10; ratio 1.48 < 1.5). Do not ship as-is.
Equity loss was cut from ~1.0 to ~0.1 points per discard and the direction is positive on every secondary check (wins +1.4 pts,
h2h >= 0), but the pooled chip gain is ~0.075 chips/hand, about what the audit implied (~1 pt x ~22% of hands x pot), and the SE
(0.051) is as large as the effect. No `final_disc.py` non-seeded build produced (only on PASS). If the owner accepts a lower bar
(the rule was pre-registered, so I did not relax it), the change is low-risk: discard path only, 1.6 ms, falls back to the blueprint.
Unexplored: the same coarse-key problem may exist in other blueprint tables (flop bucket by best pair only).

## 7. Addendum: MATCH WINS tables (owner rule; match = one duplicate pair, win if chips>0). Full text: `results/disc1/wins_tables.txt`, `tools/disc1_wins.py`
Stage 1 (200h legs), W = wins out of N matches, base -> cand (ties .5):
- ALL 18 bots (N=720): 457.0 (63.5%) -> 467.0 (64.9%), +1.4pp +-1.9; chips +0.075 +-0.051.
- TOUGH group (D1's 7: conv_opp3, new_eqrandom, new_exploiter, new_geometric, new_minraise, potctl + lakshya1 200h run now; N=280):
  159.0 (56.8%) -> 166.0 (59.3%), +2.5pp +-3.0; chips +0.099 +-0.063.
  conv_opp3 19->23, new_eqrandom 20->23, new_geometric 19->24, potctl 26->29, new_minraise 20->19, lakshya1 26->26, new_exploiter 29->22.
- NON-TOUGH (N=480): 324.0 (67.5%) -> 327.0 (68.1%), +0.6pp +-2.3; chips +0.064 +-0.068.
  Hurt: new_rules 31->26 (-12.5pp +-7, chips -0.02), betfold 36->32 (-10pp +-7, chips -0.17), donk 30->27 (-7.5pp). Helped: new_trapper 19->26 (+17.5pp).
- Down by > 2 SE in win rate: new_exploiter (tough group): -17.5pp +-9 (about -1.9 to -2.0 SE, borderline); no other bot.
Stage 2 (500h legs): lakshya1 13.0->9.0 of 24 (-16.7pp +-10; chips -0.14 +-0.20); new_eqrandom 12.0->14.0 of 24 (+8.3pp; chips +0.12). Pooled 25.0->23.0 of 48.
Head-to-head cand vs base (200h): cand wins 24/40 = 60%.
Against the updated PRIMARY METRIC (+2.0pp pooled wins, no bot down > 2 SE, lakshya1 500h wins not lower, h2h >= 50%): pooled all-bots +1.4pp (miss),
lakshya1 500h wins lower (13 -> 9; miss), new_exploiter borderline: still FAIL. Tough group +2.5pp +-3.0 is positive but not distinguishable from 0.
