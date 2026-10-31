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
