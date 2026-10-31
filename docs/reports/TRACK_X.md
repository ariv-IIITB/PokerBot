# Track X (exploit layer): reports

Plan: `docs/CFR_BUILDMAP.md` §3. Branch `x/exploit-layer`.

## X0. Recorded evidence and fixtures (2026-10-31)

**What:** `lab/opps/record.py` plays our in-process brain against each opponent in duplicate pairs
and saves every hand from our side (seat, the 3 dealt and 2 kept hole cards, board, every action
with street and amount, revealed discards, the opponent's shown cards, our chip result) as
gzipped JSON. `lab/opps/traits.py` turns records into the book's profile table
(`docs/book/pokerbot_book.html` §2.8). The original profiling scripts lived in a scratchpad on
another machine, so both were rewritten; the definitions were then checked against the book.

**Fixtures:** `tests/fixtures/opp_records/<bot>.json.gz`, 2 duplicate pairs (4 matches × 400 hands)
per bot: the 6 training bots, `starter`, `calling_station`, `tight`, `maniac`, `random_legal`,
`all_in`. 552 KB in all. Held-out bots are **not** recorded (never tuned on). Recorded with Tier 3,
lock off, `discard_holdem`, commit `0306371` + X0.

**Test:** `tests/test_opp_traits.py`, 20 tests: one per column definition on hand-built hands, the
recorder round trip, a live 6-hand recording, and the fixtures against the book's table within
3 binomial SE + 0.06 for every column with ≥ 20 observations.

**Numbers** (12 pairs = 9,600 hands per bot, Tier 3 lock off; book values in brackets where they differ by more than 2 points):

| opponent | Tier 3 chips/hand | wins | VPIP | PFR | fold flop | turn | river | bets river (unfaced) | after our check | shown river bets weak | WTSD | discards lowest |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| d_conv_opp3 | −1.50 ± 0.41 [−1.13] | 25% | 83% | 35% | 42% | 67% | 70% | 47% | 65% | 21% | 22% | 63% |
| d_new_rules | −1.52 ± 0.27 [−0.84] | 21% [33%] | 77% | 41% | 63% | 55% [59%] | 57% | 35% | 30% | 4% | 42% [38%] | 62% |
| d_new_lag | +5.18 ± 0.65 [+5.80] | 88% [96%] | 90% | 60% | 12% | 19% | 38% | 67% | 69% | 20% | 40% | 59% |
| d_new_trapper | +0.06 ± 0.38 | 54% [42%] | 49% | 3% | 30% | 23% | 23% | 24% | 38% | 0% | 63% | 64% |
| d_new_exploiter | −1.37 ± 0.35 | 29% [17%] | 80% | 32% | 64% | 80% | 79% | 35% | 31% | 3% | 25% | 62% |
| d_new_minraise | +0.26 ± 0.34 | 54% | 79% | 52% | 47% | 39% | 44% | 44% | 38% | 4% | 45% | 68% |
| starter | +19.09 ± 0.47 | 100% | 80% | 0% | 0% | 0% | 0% | 0% | 0% | — | 100% | 100% |
| calling_station | +22.21 ± 0.57 | 100% | 80% | 0% | 0% | 0% | 0% | 0% | 0% | — | 100% | 36% |
| tight | +6.48 ± 0.33 | 100% | 42% | 9% | 32% | 31% | 8% | 37% | 32% | 11% | 50% | 40% |
| maniac | +49.04 ± 0.88 | 100% | 96% | 74% | 2% | 2% | 3% | 70% | 69% | 52% | 69% | 36% |
| random_legal | +18.14 ± 0.72 | 100% | 65% | 36% | 35% | 43% [38%] | 45% | 50% | 50% | 51% | 37% | 37% |
| all_in | +24.96 ± 0.96 | 100% | 100% | 100% | — | — | — | — | — | — | 100% | 37% |

**Findings**

- Every opponent-behaviour column reproduces the book within ~2 points except a few within 4–5
  (noise at these n). Tier 3's own results moved more (rules −1.52 vs −0.84, trapper wins 54% vs 42%):
  Tier 3 changed since the book's run (the `ba5800f` fix), so those columns are not tested.
- **The book's "bets river when checked to" column is really "bets the river when not facing a
  bet"** (leads included): with that definition all bots match within 1 point; strictly after our
  check, conv_opp3 bets 65% (book column 46%) and the trapper 38% (24%). `lab.opps.traits` reports
  both (`bet_river`, `bet_river_after_check`). For X3, the after-check number is the one that
  matters for our check-then-call decisions: conv_opp3 bets 65% of rivers we check to it, yet only
  21% of its shown river bets are weak. Whether it folds those bets to a raise is not measured yet.
- Runtime: about 30–100 s per bot for 12 pairs on 6 processes.

Commands:

```
.venv/bin/python -m lab.opps.record --pool train,starter,calling_station,tight,maniac,random_legal,all_in \
    --pairs 12 --processes 6 --out logs/records
.venv/bin/python -m lab.opps.traits logs/records/*.json.gz [--fixtures tests/fixtures/opp_records]
```

## X1. Trait detectors in `bot/` (2026-10-31)

**What:** `bot/strategy/traits.py` (stdlib only): Wald SPRTs (α = β = 0.05, bounds ±log 19) for
three traits, a CUSUM after each verdict (threshold 5 nats; an alarm restarts the trait), and
rates shrunk toward the prior (K = 15).

| trait | observation | H0 / H1 |
|---|---|---|
| `overfolder` | folds, per decision facing our postflop bet or raise | 0.40 / 0.60 |
| `station` | calls or raises, per decision facing our river bet or raise | 0.50 / 0.80 |
| `preflop_folder` | folds to our first-in preflop raise | 0.35 / 0.55 |

`Opponent.observe` (`bot/opponent.py`) feeds it from the same message stream as `OpponentModel`
(on each `OppAction` it classifies the last action from `state.hand.history`); errors are caught and
logged. **Nothing reads the verdicts yet** (X3 will), so play is unchanged.

**Tests:** `tests/test_strategy_traits.py`, 39: SPRT bounds and steps, shrinkage, a style switch (75 % →
20 % folds) trips the CUSUM within 40 decisions, no alarm on a steady 70 % folder (20 seeds), event
classification, the bot's events equal X0's lab definitions on every fixture hand (> 50,000 decisions),
and the verdicts below replayed through `Opponent.observe`.

**Verdicts on the X0 fixtures** (4 matches each; `y@107` = settled on "yes" from hand 107 on):

| bot | over-folder | station | preflop folder |
|---|---|---|---|
| d_conv_opp3 | y@107 y@140 y@35 y@145 | n n n n | n n n n |
| d_new_rules | y@247 y@139 y@19 y@36 | n n n n | n n n n |
| d_new_exploiter | y@31 y@125 y@31 y@43 | n n n n | n n n n |
| d_new_lag | n n n n | n n n n | n n n n |
| d_new_trapper | n n n n | y@61 y@45 open y@249 | n n n n |
| d_new_minraise | n n n open | n n n n | n n n n |
| starter / calling_station | n (by hand 10) | y@12–27 | n |
| tight | n | y@46–65 | y@26–219 |
| maniac | n | y@44–84 | n |
| random_legal | n | n | n |

This matches the book's identification table (§2.9): over-folders at ~35–145 hands, stations in
~13–27. CUSUM alarms: 0 in most matches, at most 2 (minraise, near the over-folder threshold).

## X2. Type posterior (2026-11-01)

**What:** `bot/strategy/types.py` (NumPy): naive Bayes over the opponent's decisions, P(action ∈ {fold,
passive, raise} | street, facing our bet, type), log-likelihood × 0.5 (naive Bayes is over-confident),
uniform prior. The library (`data/discard_holdem/types.json`, 6.5 KB, embedded as `ARTIFACTS["types"]`
by `tools/embed_data.py`) is built by `lab/opps/types.py` from recorded pairs 2–11 (pairs 0–1 are the
test fixtures, so they are held-out seeds):

| type | family | river bluff share | river bets (unfaced) |
|---|---|---|---|
| exploiter, conv_opp3, rules | over-folder | 3 %, 23 %, 4 % | |
| minraise | value-only | 4 % | |
| tight | nit | 11 % | |
| station (starter = calling_station) | station | 0 % | 0 % |
| trapper | trapper | 0 % | |
| lag, maniac | aggressor | 20 %, 52 % | |
| unknown | population average, flattened 50 % toward uniform | 21 % | 27 % |

**Unseen styles.** A first version with pooled family types matched random_legal to "value-only" with
probability 1.00 (it would then have folded bluff-catchers against a bot that bluffs half its rivers).
Fix: one type per bot plus a **fit check**: the KL (per decision) from the observed actions to the best type,
minus its sampling bias df/2N, is −0.016…+0.020 for every library bot on held-out seeds, +0.09…+0.17 for
random_legal and +0.35 for all_in. Mass moves to "unknown" linearly between 0.03 and 0.06.

`Opponent.observe` builds the posterior on the first message that brings the rules and feeds it (errors
caught; a broken library leaves it None). **Nothing reads it yet** (X3 will), so play is unchanged.

**Held-out seeds** (fixtures, 4 matches each): the right family at hand 400 in 4/4 matches for every
training/sparring bot, at hand 100 in ≥ 3/4; random_legal and all_in end "unknown" (≥ 0.76 by hand 50,
1.00 by 400). Over-folders' implied river bluff share 3–4 % (exploiter, rules), maniac 52 %.

**Tests:** `tests/test_strategy_types.py` (17). Fast suite 1260 passed, 2 skipped.

## X3. Counter-moves with lambda (2026-11-01; code done, gate X pending)

**What:** `bot/brains/exploit.py`: `adjust(p, street, traits, types)`, a pure function over a brain's
already opponent-adjusted parameters. No evidence → the same dict back (Tier 3 exactly).

| move | evidence → lambda | effect at lambda = 1 |
|---|---|---|
| over-folder | X1 SPRT "yes"; ramps 0 → 1 over 20 more observations; 0 again on a CUSUM alarm | pure-bluff frequencies (`cbet_air_wet`, `stab_dry_freq`, `stab_wet_freq`, `barrel_bluff_prob`, Tier 2's `bluff_freq`) → 0.60; river bluffs × 2.5 (`river_air_share` / 2.5) |
| value-only river bettor | X2 posterior mass on types with ≤ 10 % river bluffs: 0.7 → 0.9 maps to 0 → 1, × min(1, decisions / 60) | river `call_margin` + 0.12 |

`bot/brains/tier3x.py`: `tier3x` = Tier 3 with the layer on top of `adjusted()` (errors → Tier 3's params;
`stats` counts the decisions each move touched). Registered in `bot/main.py` (not the default).
Not built yet: the station, preflop-folder and trapper moves (stations are already beaten by +20
chips/hand; no training bot is a preflop folder).

On the held-out fixture seeds the value-only move switches on for exploiter, rules and minraise (λ > 0.5 by
hand 400) and stays off for maniac, lag and random_legal.

**Tests:** `tests/test_exploit.py` (14). Fast suite 1274 passed, 2 skipped.

**Gate X (to run):** `lab.eval tier3x --pool train --pairs 50 --first-seed 8000 --locks on` against the G8
re-check's `logs/g/recheck/pool_t3.txt` (same seeds), then fresh seeds; also tier2, starter and sparring bots.
