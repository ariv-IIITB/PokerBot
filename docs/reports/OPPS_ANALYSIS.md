# LLM-built opponents: analysis and results (2026-10-28)

Four bots in `Opps/`, each made by a major LLM from a single prompt ("build this bot, it
shouldn't fail, make it win, here are the rules"). Goal: find what such bots have in
common, exploit it, and take whatever they do better than Tier 2.

## 1. Bottom line

- **Tier 2 beats three of the four easily** (opp1, opp2, opp4: 86-100% of matches).
- **Tier 2 loses badly to opp3**: 12-15% of matches, **-2.73 ± 0.33 chips/hand** with the
  endgame locks off (about -1.4 bb/hand). opp3 is the one bot that plays a normal,
  aggressive style: it raises preflop, iso-raises limps and bets most flops.
- **No single Tier 2 setting fixes it.** Calling more, raising more preflop, dropping the
  big-bet penalty, or all of these together: none beat the unchanged bot (section 6).
  Turning off range inference makes it far worse (-8.2). The leak is structural.
- The LLM "pattern" is real (section 5) and Tier 2 already wins against it. **The threat
  is the stronger LLM bots like opp3**, and some of the field will look like it.

## 2. Setup

- Adapters: `lab/opps/__init__.py` seats each bot as a lab brain (`opp1`..`opp4` in
  `lab/players.py`). The bots' own files are unchanged.
- Variant: `lab/opps/holdem_100bb.json`, MIT-style heads-up NL Hold'em: blinds 1/2,
  stacks 200 (100 bb), reset every hand, 400 hands per match. That's what the bots were
  written for (opp1 hardcodes the 200 stack).
- Duplicate deals (`lab.harness`): each seed is two 400-hand matches with seats swapped.
  ± is one standard error over duplicate pairs.
- Python 3.12 (system); this machine has no 3.11 / `.venv`. Fine for lab matches.
- 0 illegal actions and 0 forfeits in every run below.

**Bugs in the bots themselves** (found while wiring them up):
- **opp2 cannot start**: `opponent_model.py` imports `TOTAL_COMBOS` from `preflop.py`,
  which doesn't define it. In a real match it crashes at import and forfeits. The adapter
  patches that one name so we can study its play.
- **opp2, opp4** expose `get_action(dict)`, not the MIT `get_action(game_state,
  round_state, active)`. Under an MIT-style engine they would likely crash on the first
  decision. (They may not have been given the starter code.)
- opp1: `fold_to_open` / `fold_to_cbet` never update, so its nit-exploit and flop bluff
  never fire. opp2: no opponent stat ever updates; its "match won, just fold" check uses
  this hand's stacks instead of the match score (late in a match, a big bet makes it fold
  anything). opp4: records the wrong event as fold-to-bet, so the stat drifts to 0 and it
  stops bluffing.

## 3. Results

### Locks on (as in the tournament), 100 pairs = 200 matches each
| Opponent | Tier 2 match score | chips/hand |
|---|---|---|
| opp1 | **0.980 ± 0.010** | +0.24 ± 0.04 |
| opp2 | **1.000 ± 0.000** | +0.28 ± 0.01 |
| opp3 | **0.120 ± 0.023** | -0.32 ± 0.02 |
| opp4 | **0.890 ± 0.022** | +0.33 ± 0.06 |

Chips/hand are small here because both sides stop playing once a match is won.

### Locks off (real chip edge), 50 pairs = 100 matches each
| Opponent | chips/hand | bb/hand | match score |
|---|---|---|---|
| opp1 | +4.40 ± 0.16 | +2.2 | 0.980 ± 0.014 |
| opp2 | +7.74 ± 0.26 | +3.9 | 1.000 ± 0.000 |
| opp3 | **-2.73 ± 0.33** | **-1.4** | 0.150 ± 0.036 |
| opp4 | +1.41 ± 0.15 | +0.7 | 0.860 ± 0.035 |

Raw output: `logs/tier2_vs_opps_100seeds.txt`, `logs/tier2_vs_opps_nolock_50seeds.txt`.

## 4. How each bot plays (action profiles, locks off)

Share of decisions by spot. Preflop "open" = first action on the button; "vs raise" =
facing a raise. Postflop "checked to" shows the bet rate (R), "vs bet" the fold rate (F).
Small samples (4-6 matches each): read them as styles, not exact rates.

| Spot | Tier 2 (vs opp3) | opp1 | opp2 | opp3 | opp4 |
|---|---|---|---|---|---|
| Button open: raise / limp / fold | **3% / 97% / 0%** | 74 / 20 / 6 | 90 / 0 / 10 | 57 / 33 / 10 | 51 / 0 / 49 |
| BB vs limp: raise | 4% | 23% | 0% | **52%** | 25% |
| Facing preflop raise: call / fold | **85% / 13%** | 64 / 24 | 87 / 6 | 50 / 39 | 23 / 64 |
| Flop checked to: bet | 35% | 32% | 61% | **63%** | 58% |
| Flop vs bet: fold | **54%** | 26% | 25% | 57% | 54% |
| Turn vs bet: fold | 54% | 26% | 29% | 60% | 58% |
| River checked to: bet | 43% | 21% | 33% | 46% | 25% |
| River vs bet: fold | 55% | 38% | 34% | 80% | 66% |

Tier 2's preflop is the same against every opponent (limp 97%, call raises 82-91%).
Raw output: `logs/profiles_tier2_vs_opps.txt`, `logs/profile_tier2_vs_opp3.txt`.

## 5. The common LLM pattern

1. **Calling rule = equity ≥ pot odds + a small margin.** opp1 and opp2 compute equity vs
   a *random* hand, so any pair looks strong: opp1 folds only 26% to flop and turn bets.
2. **Raises are value-only.** Postflop raises need 74-90% equity; bluff-raises are rare.
3. **Small fixed bet sizes**, 33-75% pot. Nobody sizes from measured fold rates.
4. **Wide, small button opens** (51-90% raise at 2-3.5 bb).
5. **Opponent stats mostly broken** (3 of 4), so the bots play their priors all match.
6. **Not all crash-proof**: 2 of 4 would likely forfeit under the real engine API.

How Tier 2 beats it: it bets for value and folds to their (honest) bets. Against
value-only bettors, folding a lot is correct.

**How opp3 is different:** it actually bluffs (63% flop bets, plenty of air), iso-raises
limps (52%), and its stats work. Against it, Tier 2's "fold when they bet" habit and its
passive preflop cost chips every hand.

## 6. Why Tier 2 loses to opp3: what we tested

Tier 2 config variants vs opp3, locks off, 20 pairs = 40 matches each
(`logs/tier2_variants_vs_opp3.txt`):

| Variant | Change | chips/hand | match score |
|---|---|---|---|
| base | none | -1.71 ± 0.44 | 0.175 |
| no_inference | range inference off | **-8.23 ± 0.23** | 0.000 |
| no_pressure | no big-bet call penalty | -3.01 ± 0.54 | 0.075 |
| looser_call | call margin -0.04, no penalty | -3.46 ± 0.85 | 0.150 |
| raise_pre | preflop raise threshold 0.70 → 0.55 | -2.38 ± 0.47 | 0.050 |
| combo | the last two together | -2.64 ± 0.77 | 0.200 |

What this says:
- **Inference is Tier 2's main strength**: without it, opp3 crushes it (-8.2).
- **Simply calling more makes it worse**: opp3's turn/river bets are mostly real, so
  calling the flop lighter just loses more later. The fix is not "fold less" everywhere.
- **Raising more preflop alone doesn't help**: Tier 2 has no plan after raising (no
  c-bet strategy, no 3-bet ranges); it's an equity-threshold bot.
- **Not yet measured: where the chips actually go** (preflop calls then folds? flop
  folds? losing showdowns?). That's the first next step (section 9).

My reading (judgement, not yet measured): Tier 2 plays every hand passively, calls opp3's
raises with hands it later gives up, and almost never takes the initiative, so opp3 wins
most small and medium pots without a showdown. Fixing that needs a real preflop strategy
(open-raise or fold on the button, 3-bet vs wide opens, fold more vs raises) and an
initiative plan postflop (c-bet when we raised, raise opp3's frequent flop bets), not
threshold tweaks.

## 7. Exploits against the common pattern

Ranked by expected value vs effort (judgement):

1. **Value bet bigger vs random-equity callers** (opp1/opp2 style): they barely fold more
   to big bets. Pick size from measured fold rate per size (see 8.3).
2. **Fold medium hands to their raises.** Their raises are value-only. Tier 2 already
   does this; keep it.
3. **3-bet their wide, small button opens** with a value + blocker range; most fold
   too much or call too much in a predictable way.
4. **Barrel against range-narrowers** (opp4 style): after two bets it reads us as very
   strong and over-folds.
5. **Late-match pressure vs buggy match locks** (opp2-style): don't rely on it; it's one bot's bug.

## 8. What to take from each bot

1. **opp3, preflop structure** (`Opps/opp3/pb/strategy.py`, `preflop()`): button
   raise-or-fold with a percentile cutoff that moves with the opponent's fold-to-open and
   3-bet rates; BB iso-raises limps; light 3-bets vs openers who fold to 3-bets. This is
   what beats us.
2. **opp3, river-bluff stat** (`Opps/opp3/pb/opponent.py`, `river_bluff`): after each
   showdown, was their river bet weak? Calls get lighter if so. Cheap and directly useful
   next to Tier 2's inference trust.
3. **opp4, bet-size choice by expected value** (`Opps/opp4/strategy.py`,
   `evaluate_bet_candidates`): try 33% / 66% / 110% / all-in and pick the best EV. Their
   fold model is broken; ours would use measured fold rates per size bucket.
4. **opp3, no awkward leftovers** (`_raise_amount`): shove when the stack left behind
   would be small next to the pot.
5. Not worth taking: push/fold charts (stacks reset every hand), opp4's match-utility
   formula (it's monotone in EV, so it changes nothing), opp1's draw-bonus (our sim
   equity already counts draws).

Write all of this in our own code; the code review requires original code.

## 9. Proposed next steps

Each step is tested against all four bots (locks off, ≥ 20 pairs each); keep a change
only if it helps against opp3 **without losing more than noise against opp1/2/4**.

1. **Chip accounting vs opp3**: where Tier 2 loses chips (by street and by how the hand
   ended). Cheap, and tells us which fix comes first.
2. **Preflop strategy for Tier 2**: button raise-or-fold, BB iso-raise and 3-bet ranges,
   tighter calls vs raises (from 8.1).
3. **Postflop initiative**: c-bet when we were the preflop raiser; raise some of the
   opponent's flop bets when they bet very often.
4. **Bet sizing from measured fold rates** (8.3 + 7.1).
5. **Grow the pool**: more LLM bots from other models/prompts; keep some held out and
   never tune on them.

## 10. Is repeating this process a good enough edge?

Yes, it's probably our strongest edge, with two conditions:

- **The pool must look like the field.** Four bots is a small sample, and tuning against
  them risks overfitting (opp3 alone could pull us somewhere odd). Generate more bots
  (different models, different prompt wordings) and keep a held-out set we never tune on.
  A change counts only if it holds on the held-out bots.
- **Do it again on reveal day.** These bots play Hold'em; the real event is a variant. On
  day 1, generating 4-6 LLM bots for the revealed variant takes minutes, and then we have a
  realistic sparring pool for the 3 days. Most teams will test against nothing, or only
  against simple baselines. Rehearse this loop now so it runs in hours, not days.

It doesn't make winning certain: duplicate deals remove most card luck, but some teams
will build bots we haven't imagined. It does turn "guess what the field does" into
something we can measure.

## Reproduce

```bash
python3 -m lab.harness tier2 opp1 opp2 opp3 opp4 --variant lab/opps/holdem_100bb.json --seeds 100 --hands 400
python3 -m lab.opps.variants opp3 20                 # Tier 2 variants, locks off
python3 -m lab.opps.variants opp1 50 base            # one opponent, locks off
python3 -m lab.opps.profile tier2 opp3 3             # action profile
```

Files added/changed: `lab/opps/__init__.py` (adapters), `lab/opps/holdem_100bb.json`,
`lab/opps/profile.py`, `lab/opps/variants.py`, `lab/players.py` (registry), `logs/`
(results), this report. Nothing in `bot/` changed.
