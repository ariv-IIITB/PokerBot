# Tier 3 ("Ivey" style) on Discard Hold'em: Phase G results

`bot/brains/tier3.py` (`Tier3Brain(Tier2Brain)`, registered as `"tier3"`). **Since G8 (2026-10-30)
`tier3` is the default brain** (`bot/main.py:DEFAULT_BRAIN`; upload candidate #4,
`dist/upload4_phaseG.zip`). Every behaviour is a flag or number in `tier3.DEFAULTS`; `"t3": false` is the
shipped Tier 2 (same parameters, every decision goes to `Tier2Brain.play`: `tests/test_tier3.py`).
To revert: `DEFAULT_BRAIN = "tier2"` and rebuild the package.

**Summary.** Tier 3 beats Tier 2 head-to-head (locks on, 100 pairs: match score 0.670 ± 0.033), is
better on the training pool (locks on: +1.57 ± 0.54 chips/hand summed, mean match score 0.62 vs 0.55,
no bot drops) and on the held-out pool (+1.16 ± 0.50, better on all three). **But both brains still
lose chips to most of the Discard Hold'em pool** (river showdowns, as in the old Hold'em finding), so
the next gains are in river play against value-heavy bettors, not in style.

Order of work: the first sections (the fix, the value floor) used only non-pool opponents (sparring
bots, `starter`, `tier1`, `tier2`), before the held-out split existed; no `d_*` or `opp1`–`opp4`
result was read until the split was fixed. The pool sections follow.

Method: `lab.eval tier3:<config> --pool ... --pairs N --locks off --variant discard_holdem
--report accounting,profile` (script: `tools/g_eval/ablate.sh`), configs compared in one batch, one
eval at a time on 4 cores. Numbers are chips/hand ± SE over duplicate pairs (400 hands each).
Logs: `logs/g/`.
Deviation: the locks-on head-to-head (`logs/g/final/h2h_lockson.*`) shared the CPU with a ~40 s test run
near its end (and `tier3.py` gained a flag that defaults off, so play is unchanged); the run is
wall-clock based, so it may be very slightly affected.

## What each part does

| Part | Flag | What it does |
|---|---|---|
| Pot maths | — | `bot/strategy/potmath.py`: `required_fold`, `mdf`, `bluff_share`, `spr` (unit tests with the plan's numbers). |
| Texture | — | `bot/strategy/texture.py`: board texture (paired, suits, connectedness, a 0..1 wet score), draw features of the best 2-card keep (flush/straight draws, backdoors, overcards), blocker score. |
| Preflop (G2) | `t3_preflop` | `bot/strategy/preflop.py`: per-class strength (equity percentile from the 3-card table) blended with a computed playability score; four spots (button open, BB vs limp, BB vs open, button vs 3-bet) are [fold, passive, raise] probability tables with linear blends at every cutoff. 3-bets / 4-bets = value top + blocker/playability bluffs. Raise-cap aware via `legal`. Facing a 4-bet or a shove: Tier 2 decides. |
| Own range | — | `bot/strategy/ranges.py`: our hand's percentile inside the range our preflop line contains (300 sampled hands weighted by the tables' action probabilities). |
| Flop (G3/G4) | `t3_flop` | As preflop raiser: small range c-bets on dry/paired boards, polarised 70 % bets on wet boards, medium hands check back on low connected boards. Facing a bet: raise value and strong draws, continue with the top MDF slice of our range (×0.95), floats in position. Small stabs when checked to in position. |
| Turn (G5) | `t3_turn` | Polarised barrels (70 %), floated hands bet when checked to, facing a bet: MDF ×0.90 × the bluff-index adjustment. |
| River (G5) | `t3_river` | Value-bet the top third of our range (66–100 % pot, rare 125 % overbet), bluff with air at the bluff share. **Facing a river bet is Tier 2's bluff-catching rule (the E4 bluff index), never MDF.** |
| Adaptation (G6) | `t3_adapt` | The Phase G `oppstats` spots (fold-to-open, 3-bet, fold-to-3-bet, raise-vs-limp, c-bet, fold-to-c-bet, check-raise, turn/river bet, discard habit) move the tables and frequencies; every spot has the ≥ 20-sample gate and the ±15-point cap. |
| Discard hiding (G7) | `hide_discard` | Among discards within 0.01 expected share of the best, throw the card that reveals least. **Off** (see below). |

## The fix: Tier 3 was weaker than Tier 2 against wide, big-betting players

Starting point (8 pairs, locks off): Tier 3 beat Tier 2 head-to-head, but won much less than Tier 2
against maniac (+28 vs +54), random_legal (+13 vs +22) and all_in (+19 vs +23).

**Diagnosis** (`logs/g/diag_*`, `logs/g/abl/`). Against maniac Tier 3 folded 30 % preflop facing a raise
(Tier 2: 4 %) and 48 % on the flop facing a bet (Tier 2: 17 %); it reached far fewer of the
showdowns it wins (showdown wins +45.7 vs +77.5 chips/hand). Street ablations (8 pairs):

| tier3 config | maniac | random_legal | all_in |
|---|---|---|---|
| WIP defaults | +29.95 ± 1.84 | +12.03 ± 1.00 | +19.46 ± 0.68 |
| `t3_preflop` off | +40.62 ± 0.75 | +16.09 ± 0.73 | +24.47 ± 1.03 |
| `t3_flop` off | +35.74 ± 1.11 | +15.95 ± 0.74 | +19.49 ± 0.68 |
| `t3_turn` off | +33.34 ± 0.75 | +14.11 ± 0.96 | +19.46 ± 0.64 |
| `t3_river` off | +30.03 ± 1.22 | +12.70 ± 0.55 | +19.49 ± 0.68 |
| `t3_adapt` off | +26.61 ± 1.11 | +12.90 ± 0.77 | +19.81 ± 0.71 |
| tier2 | +53.01 ± 1.08 | +22.54 ± 1.02 | +24.29 ± 1.10 |

Cause: of the three suspects, (3) "too many folds" was it, preflop and on the flop/turn. The
preflop tables shrink defence with the raise size (`pf_defend_slope`; the button's continue range
shrinks with the 3-bet ratio), clipped at 20–25 %, so against a player who raises big with
anything Tier 3 folded hands that were clearly priced in. On the flop and turn the MDF slice
ranks hands inside **our own** range and ignores who bets. Against a player whose bets mean
nothing, the bottom of our range still has the pot odds. Suspect (1), light 3-bets shoved on,
was small (−0.6 chips/hand in preflop folds vs maniac). Suspect (2), wide MDF calls against huge
bets, runs the other way here: MDF calls *less* against big bets.

**Changes** (all flags in `DEFAULTS`):

- `eq_floor` (on): Tier 3 never folds, preflop, flop or turn, a hand that Tier 2's pot-odds rule
  would call (`equity >= pot odds + call_margin + bet_pressure × to_call/pot`, with Tier 2's
  adapted parameters, so `bet_pressure` shrinks against maniacs as in Tier 2).
- `mdf_eq_slack` 0.05 (on): an MDF call needs equity ≥ pot odds − 0.05 (suspect 2's guard).
- `bluff_tilt_scale` (on): 3-bet and 4-bet bluff mass × (1 + tilt of fold-to-3-bet), so none
  against a player who never folds to a re-raise (suspect 1's guard); the extra bluffs against
  folders are unchanged.

Result (16 pairs, seeds 0–15, `logs/g/fix1/`):

| opp | new | WIP ("old") | no `eq_floor` | no slack | no tilt scale | tier2 |
|---|---|---|---|---|---|---|
| tier2 | +2.49 ± 0.48 | +1.70 ± 0.33 | +2.69 ± 0.36 | +1.85 ± 0.32 | +2.25 ± 0.46 | — |
| tier1 | +1.59 ± 0.49 | +1.53 ± 0.41 | +1.81 ± 0.42 | +0.62 ± 0.65 | +2.39 ± 0.50 | +0.16 ± 0.44 |
| calling_station | +13.64 ± 0.24 | +14.02 ± 0.24 | +13.71 ± 0.18 | +13.62 ± 0.23 | +13.65 ± 0.20 | +8.48 ± 0.20 |
| tight | +5.61 ± 0.38 | +5.20 ± 0.26 | +5.30 ± 0.24 | +5.28 ± 0.35 | +5.68 ± 0.40 | +8.38 ± 0.38 |
| maniac | +50.93 ± 0.75 | +28.55 ± 1.03 | +28.83 ± 0.64 | +50.31 ± 0.67 | +49.95 ± 1.09 | +54.50 ± 0.73 |
| random_legal | +20.41 ± 0.56 | +12.27 ± 0.55 | +11.64 ± 0.46 | +20.15 ± 0.64 | +20.70 ± 0.49 | +23.00 ± 0.53 |
| all_in | +24.23 ± 0.79 | +18.66 ± 0.60 | +18.76 ± 0.59 | +24.26 ± 0.76 | +24.20 ± 0.77 | +23.24 ± 0.66 |
| tier0 | +1.49 | +1.47 | +1.49 | +1.49 | +1.49 | +1.04 |

`eq_floor` is the fix: +22 vs maniac, +8 vs random_legal, +5.6 vs all_in, nothing lost elsewhere.
The slack and the tilt scale are neutral within noise (no opponent moves by 2 SE); they are kept
as guards because they only bind against extreme opponents and are cheap. all_in is now on par
with Tier 2.

## Remaining gaps after the fix, and the value floor

Street ablations on top of the fix (16 pairs vs the sparring bots, `logs/g/abl2/`; 32 pairs vs
tier2/tier1, `logs/g/abl3/`):

| config | tight | maniac | random_legal | calling_station | tier2 | tier1 |
|---|---|---|---|---|---|---|
| base | +5.56 ± 0.34 | +50.58 ± 0.71 | +19.58 ± 0.67 | +13.51 ± 0.25 | +1.74 ± 0.27 | +0.53 ± 0.45 |
| `t3_preflop` off | +6.91 ± 0.36 | +50.86 ± 0.95 | +25.06 ± 0.57 | +5.12 ± 0.11 | +1.44 ± 0.23 | +1.40 ± 0.26 |
| `t3_flop` off | +6.28 ± 0.31 | +52.31 ± 0.68 | +19.19 ± 0.77 | +15.64 ± 0.33 | +1.85 ± 0.29 | −0.19 ± 0.32 |
| `t3_turn` off | +6.60 ± 0.32 | +52.73 ± 0.79 | +19.95 ± 0.61 | +16.66 ± 0.29 | +1.00 ± 0.22 | −0.56 ± 0.46 |
| `t3_river` off | +5.67 ± 0.39 | +50.29 ± 1.19 | +19.96 ± 0.57 | +15.70 ± 0.27 | +2.41 ± 0.35 | +1.08 ± 0.35 |

Reading: the postflop style earns its chips against the thinking bots (turn off: −0.7 vs tier2,
−1.1 vs tier1) but gives some back to loose callers (each postflop street off: +2 to +3 vs
calling_station). Preflop is the opposite: it wins +8 vs calling_station and loses 5.5 vs
random_legal (whose re-raises are random sizes, so the size-shrunk continue ranges fold too much
even with the floor, because the inference reads the big raises as strong). Tier 2 adapts its
value threshold and size to loose players (`value_shift`, `value_size_shift`); Tier 3's value
cut-offs are fixed and its sizes are texture-only, so it checks or under-bets hands Tier 2 bets.

**Value floor** (`value_floor`, `logs/g/vf/`, 16 pairs): postflop, a hand Tier 2 would value-raise
goes to Tier 2 (its adapted size).

| config | tier2 | tier1 | calling_station | tight | maniac | random_legal | all_in |
|---|---|---|---|---|---|---|---|
| base | +2.53 ± 0.39 | +1.10 ± 0.65 | +13.66 ± 0.23 | +5.67 ± 0.37 | +49.76 ± 0.79 | +19.25 ± 0.74 | +24.10 ± 0.78 |
| floor, Tier 2 sizes | +1.30 ± 0.54 | −1.61 ± 0.39 | +23.61 ± 0.51 | +7.69 ± 0.41 | +52.23 ± 0.86 | +20.41 ± 0.58 | +24.15 ± 0.80 |
| floor, texture sizes | +1.04 ± 0.41 | −1.66 ± 0.41 | +15.33 ± 0.28 | +6.80 ± 0.43 | +53.06 ± 0.90 | +19.98 ± 0.46 | +24.03 ± 0.80 |
| floor (T2 sizes), river style off | +1.15 ± 0.39 | −1.29 ± 0.39 | +23.40 ± 0.49 | +7.58 ± 0.45 | +52.92 ± 1.13 | +19.60 ± 0.74 | +23.96 ± 0.75 |

Always on, the floor wins +10 vs calling_station but loses 2.7 vs tier1 (~3.5 SE): dropped in that
form. The opponents it helps never fold to our turn/river bets (measured fold rate ~0.05 for
calling_station and maniac, ~0.30 for tight, 0.43–0.52 for tier1/tier2/random_legal), so it is
gated (`value_floor_gate`): applied with probability −(tilt(fold_turn) + tilt(fold_river))/2,
clipped to 0..1 (0 below the 20-sample gate; this is the plan's "calling station: value-bet three
streets" rule). Texture sizes are worse than Tier 2's sizes on every opponent but maniac.

Gated floor, fresh seeds 100–123 (24 pairs, `logs/g/vfg/`, `lab.eval --compare` verdict KEEP):

| opp | base | gated value floor | diff |
|---|---|---|---|
| tier2 | +2.05 ± 0.38 | +1.87 ± 0.36 | −0.18 ± 0.52 |
| tier1 | +1.39 ± 0.38 | +0.90 ± 0.36 | −0.49 ± 0.52 |
| calling_station | +13.87 ± 0.24 | +22.82 ± 0.43 | **+8.95 ± 0.49** |
| tight | +5.67 ± 0.38 | +6.85 ± 0.39 | **+1.18 ± 0.54** |
| maniac | +48.45 ± 0.69 | +50.15 ± 0.79 | +1.70 ± 1.05 |
| random_legal | +19.98 ± 0.42 | +19.37 ± 0.42 | −0.61 ± 0.59 |
| all_in | +26.01 ± 0.71 | +26.12 ± 0.71 | +0.11 ± 1.00 |
| starter | +11.95 ± 0.18 | +19.56 ± 0.26 | **+7.61 ± 0.32** |

No opponent drops by 2 SE: **kept** (`value_floor` on, Tier 2 sizes, gated).

Two more A/Bs, both no gain, both **off**:
- `hide_discard` (G7), seeds 200–231, 32 pairs (`logs/g/final/hide.*`): every opponent within 1.1 SE, sum
  −1.95 ± 1.95.
- `pf_size_pressure` (scale the preflop size slopes by Tier 2's `bet_pressure` adjustment, aimed at
  random_legal), seeds 300–323, 24 pairs (`logs/g/pfsp/`): random_legal −0.21 ± 0.68, nothing moves by
  2 SE.

## Final numbers: Tier 3 (defaults) vs Tier 2, same seeds

Fresh seeds 200–231, 32 pairs, locks off (`logs/g/final/`; `lab.eval --compare logs/g/final/t2.txt
logs/g/final/final.txt`):

| opp | tier2 | tier3 | diff |
|---|---|---|---|
| tier2 (head-to-head; tier2's row is self-play) | +0.45 ± 0.20 | +1.59 ± 0.30 | +1.14 ± 0.36 |
| tier1 | −0.34 ± 0.30 | +0.92 ± 0.41 | +1.26 ± 0.51 |
| calling_station | +8.58 ± 0.12 | +22.70 ± 0.32 | +14.12 ± 0.34 |
| tight | +8.67 ± 0.31 | +6.55 ± 0.34 | **−2.12 ± 0.46** |
| maniac | +52.52 ± 0.66 | +51.94 ± 0.77 | −0.58 ± 1.01 |
| random_legal | +22.46 ± 0.47 | +20.07 ± 0.49 | **−2.39 ± 0.68** |
| all_in | +23.20 ± 0.52 | +24.77 ± 0.82 | +1.57 ± 0.97 |
| starter | +7.51 ± 0.13 | +20.11 ± 0.24 | +12.60 ± 0.27 |

Match scores are 1.000 against every sparring bot and the starter, for both brains.

**Head-to-head, locks on (as shipped), 100 pairs, seeds 500–599** (`logs/g/final/h2h_lockson.*`):
Tier 3 vs Tier 2 match score **0.580 ± 0.035** over 200 matches (+0.21 ± 0.02 chips/hand; the lock
ends won matches early). That is 2.3 SE above 0.5: the plan's G8 criterion 1 is met, narrowly.

**Caveat on the head-to-head.** With the locks off, Tier 3 wins chips against Tier 2 but *loses
slightly more matches than it wins*: match score 0.391 ± 0.061 (64 matches, seeds 200–231), 0.438 ±
0.072 (48, seeds 100–123), 0.417 (48, seeds 300–323), 0.469 ± 0.090 (32, seeds 0–15). Pooled ≈ 0.42,
about 2 SE below 0.5. Tier 3 wins a few matches by a lot and loses more of them by a little. With
the endgame lock it banks those big leads, which is why the locks-on score is above 0.5. We are
scored on matches won, so the locks-on match score is the number that counts, but this skew should be
checked again on the training pool.

## Training pool (after the held-out split, 2026-10-30)

Split (chosen by style before any pool result was read, `lab/opps/discard_pool.json`): **held out**
`d_conv_opp4` (a real LLM bot: charts, EV sizes), `d_new_eqrandom` (the common weak pattern: equity vs a
random hand), `d_new_geometric` (theory: polarised sizes, MDF, the closest to Tier 3's own style).
**Training:** `d_conv_opp3`, `d_new_rules`, `d_new_lag`, `d_new_trapper`, `d_new_exploiter`, `d_new_minraise`.
Tier 2 here includes F0 (`aggr_call_shift` 0, merged from `main`), as does Tier 3 (it inherits Tier 2's
shipped parameters).

**Locks off, 50 pairs, seeds 0–49** (`logs/g/pool/`; `lab.eval --compare logs/g/pool/t2.txt logs/g/pool/t3.txt`):

| training bot | tier2 (match) | tier3 (match) | diff |
|---|---|---|---|
| d_conv_opp3 | −2.63 ± 0.25 (0.13) | −1.46 ± 0.22 (0.32) | **+1.17 ± 0.33** |
| d_new_rules | −0.87 ± 0.21 (0.39) | −0.66 ± 0.19 (0.40) | +0.21 ± 0.28 |
| d_new_lag | +7.06 ± 0.30 (0.94) | +5.94 ± 0.35 (0.87) | **−1.12 ± 0.46** |
| d_new_trapper | −1.15 ± 0.13 (0.32) | −0.29 ± 0.14 (0.42) | **+0.86 ± 0.19** |
| d_new_exploiter | −1.69 ± 0.20 (0.26) | −1.11 ± 0.21 (0.35) | +0.58 ± 0.29 |
| d_new_minraise | +0.05 ± 0.21 (0.54) | +0.13 ± 0.15 (0.54) | +0.08 ± 0.26 |
| sum | | | +1.78 ± 0.77 |

**Both brains lose to four of the six training bots.** It is the old leak again, river showdowns:
against conv_opp3, Tier 2 loses 3,610 showdowns for −5.79 chips/hand and wins 2,549 for +2.35; Tier 3
loses 3,244 (−6.06) and wins 3,172 (+3.60). Tier 3 is better on five of six; by the keep rule ("no
opponent drops by more than 2 SE") the −1.12 against new_lag fails it.

new_lag ablation (30 pairs, fresh seeds 1000–1029, `logs/g/lag/`): base +6.27 ± 0.41, tier2 +6.72 ± 0.40,
preflop off +6.30, flop off +6.73, turn off +6.52, river off +6.20, value floor off +6.24. No street
explains the gap (all within ~1 SE); pooled over both runs Tier 3 is about −0.85 ± 0.36 against new_lag,
spread over turn and river folds (Tier 3 builds bigger pots with its barrels and then folds to new_lag's
raises). Not chased further (plan: don't spiral).

**Locks on (as shipped), 50 pairs, seeds 2000–2049** (`logs/g/pool_on/`; verdict **KEEP**, sum +1.57 ± 0.54):

| training bot | tier2 chips (match) | tier3 chips (match) | chips diff |
|---|---|---|---|
| d_conv_opp3 | −2.20 ± 0.19 (0.23) | −1.48 ± 0.22 (0.41) | **+0.72 ± 0.29** |
| d_new_rules | −1.02 ± 0.17 (0.57) | −0.98 ± 0.16 (0.49) | +0.04 ± 0.23 |
| d_new_lag | +0.24 ± 0.02 (0.99) | +0.16 ± 0.05 (0.97) | −0.08 ± 0.05 |
| d_new_trapper | −0.71 ± 0.14 (0.47) | −0.03 ± 0.12 (0.74) | **+0.68 ± 0.18** |
| d_new_exploiter | −1.62 ± 0.23 (0.35) | −1.40 ± 0.19 (0.39) | +0.22 ± 0.30 |
| d_new_minraise | −0.39 ± 0.10 (0.68) | −0.40 ± 0.12 (0.74) | −0.01 ± 0.16 |
| mean match score | 0.548 | **0.623** | |

With the lock (it ends won matches early, so chips against new_lag shrink to ~0) Tier 3 wins more
matches against four of six and no opponent drops; the new_lag gap is a match-score 0.99 → 0.97.

**Held out, one `--final` run, locks on, 50 pairs, seeds 3000–3049** (`logs/g/heldout/`; the plan says 100
pairs, cut to 50 for time: ~4 h of wall clock for both brains):

| held-out bot | tier2 chips (match) | tier3 chips (match) | diff |
|---|---|---|---|
| d_conv_opp4 | −0.76 ± 0.18 (0.64) | −0.20 ± 0.15 (0.70) | **+0.56 ± 0.23** |
| d_new_eqrandom | −0.38 ± 0.15 (0.71) | −0.12 ± 0.13 (0.74) | +0.26 ± 0.20 |
| d_new_geometric | −2.45 ± 0.24 (0.40) | −2.11 ± 0.31 (0.48) | +0.34 ± 0.39 |
| sum | | | +1.16 ± 0.50 |

## G8: ship decision

| Criterion | Result | |
|---|---|---|
| 1. Beats Tier 2 head-to-head (locks on, 100 pairs, match score > 0.5 by 2 SE) | 0.670 ± 0.033 over 200 matches (seeds 600–699, both with F0; `logs/g/final/h2h_lockson_f0.*`). Before F0: 0.580 ± 0.035 | met |
| 2. Better on the training pool, locks on and off | on: +1.57 ± 0.54, no drop; off: +1.78 ± 0.77, but d_new_lag −1.12 ± 0.46 (−0.45 ± 0.57 on fresh seeds) | met on, nearly met off |
| 3. Held-out not worse than Tier 2 | +1.16 ± 0.50, better on all three | met |
| 4. Timing and memory at 400 and 1000 hands | package: projected 2× bank use 27–33 %, worst reply 42 ms (projected), 42 MB | met |

**Decision: Tier 3 ships** (`DEFAULT_BRAIN = "tier3"`, upload candidate #4). The one soft spot is
criterion 2 with the locks off against new_lag (a loose-aggressive bot both brains beat 87–99 % of the
time). The lock is on in the real match.

## Kept / dropped

| Change | State | Evidence |
|---|---|---|
| `eq_floor` | **kept, on** | +22 maniac, +8 random_legal, +5.6 all_in (16 pairs, ≫ 2 SE), nothing lost |
| `mdf_eq_slack` 0.05 | kept, on (guard) | neutral within noise |
| `bluff_tilt_scale` | kept, on (guard) | neutral within noise |
| `value_floor` + `value_floor_gate`, Tier 2 sizes | **kept, on** | +9 calling_station, +7.6 starter, +1.2 tight; no drop > 2 SE (24 pairs, fresh seeds) |
| `value_floor` ungated | dropped | −2.7 vs tier1 (~3.5 SE) |
| `value_floor_size: "t3"` (texture sizes) | dropped | worse than Tier 2 sizes everywhere but maniac |
| `hide_discard` (G7) | dropped, off | no gain (32 pairs) |
| `pf_size_pressure` | dropped, off | no gain vs its target random_legal (24 pairs) |
| street flags `t3_preflop/flop/turn/river`, `t3_adapt` | all on | mixed by opponent (tables above); each wins somewhere and loses somewhere, none is a clear net loss |

**Open gaps** (Tier 3 below Tier 2 by more than 2 SE): tight −2.1 and random_legal −2.4. From the
ablations: vs random_legal the loss is preflop (the size-shrunk continue ranges plus inference that
reads random big raises as strong); vs tight it is spread over the postflop streets (tight never
bluffs and calls any pair against bets up to half the pot). Both are still won 100 % of matches.
Whether they matter depends on the real pool, which is untested here by design.

**Next:** both brains lose to d_conv_opp3, d_new_rules, d_new_exploiter (training) and d_new_geometric
(held out) in chips; the accounting shows the losses at river showdowns (more showdowns lost than won,
and bigger). That is where the next work should go. The Phase E re-check on the pool
(`tools/f_eval/run_f2.sh recheck`) was not run.

## Checks

- Fast suite: `.venv/bin/python -m pytest -n 4`: **1163 passed, 2 skipped** (after the F0 merge, the rebuilt tables and the default switch).
  (`tests/test_tier1.py::test_tier1_beats_random_and_plays_legally` failed once under `-n 4` and passed 3/3 alone: the known load-sensitive test.)
- `tests/test_timing_slow.py -m slow -n 3`: **10 passed** (4 new Tier 3 cases: self-play 400 hands,
  vs tier2 1000 hands, vs maniac and calling_station; the engine charges every reply ×2).
- Bank use at 2× (seed 6, locks off): Tier 3 23 % (self-play, 400 hands), 24 % (1000 hands vs tier2),
  26 % vs maniac, 27 % vs calling_station; Tier 2 self-play 24 %. Worst reply 0.04 s. The own-range
  sample costs little.
- Memory (`lab.memory_check --hands 400`): Tier 3 43.1 MB, Tier 2 40.9 MB peak RSS.
- `tests/test_timing_slow.py -m slow`: 10 passed again after the default switch (the real subprocess bot is now Tier 3).
- `tools.package_submission --zip --stage2` **with Tier 3 as the default and the tables** (rebuilt with
  `lab.precompute --variant discard_holdem --samples 6000 --range-top 0.3`; `tests/test_embed.py` passes, so the
  committed `bot/embedded.py` matches them): all checks pass, 190 KB, projected 2× bank use 27–33 %, 41.8 MB.
  Saved as `dist/upload4_phaseG.zip` (sha256 in `docs/SUBMISSIONS.md`).
- `tests/test_tier3.py` (new): registration and default brain, Tier 3 inherits the shipped Tier 2
  parameters (and follows a change to `tier2.json`), `"t3": false` never enters Tier 3's code,
  legality and no style exceptions vs five bots, the equity floor never folds a priced call (vs
  all_in and maniac), the bluff-mass and value-floor gates, the Tier 2 call rule.
  An exact-chips equivalence test was tried and dropped: the fast discard and the rollouts size
  their sample batches by the clock, so two runs differ under CPU load even with sample caps.

## Code changes in this step

- `bot/brains/tier3.py`: `eq_floor`, `mdf_eq_slack`, `bluff_tilt_scale`, `value_floor`
  (+ `_gate`, `_size`), `pf_size_pressure` and `pf_ratio_slope` (off / unchanged default); `defaults()`
  starts from Tier 2's loaded parameters; `stats["t3_errors"]` counts style exceptions
  (`t3_fallbacks` also counts the spots Tier 3 leaves to Tier 2 on purpose).
- `tests/test_tier3.py` (new), `tests/test_timing_slow.py` (Tier 3 cases).
- `tools/g_eval/ablate.sh`: runs a list of configs against a list of opponents (`FIRST_SEED`, `LOCKS`, `FINAL`).
- `lab/opps/discard_pool.json` (the split; replaces `discard_pool_draft.json`).
- Merged `main` (F0: Tier 2 `aggr_call_shift` 0, the package no-tables guard).
- `tools/package_submission.py`: the no-tables guard applies only to the active variant (F0's guard refused every
  catalog variant without tables; 3 tests failed on `main`); the default `--brain` follows `bot/main.py`.
  New test `tests/test_day1.py::test_the_package_refuses_the_active_variant_without_its_tables`.
- `bot/main.py`: `DEFAULT_BRAIN = "tier3"` (G8).
