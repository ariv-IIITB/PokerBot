# Discard Hold'em opponent pool: design, health and Tier 2 baseline (Phase F v2, 2026-10-29)

Phase F v2 replaces the original Phase F (the user generating LLM bots by hand). The pool lives in
`Opps/discard/<name>/bot.py`, every bot runs as `python3.11 bot.py` over the real protocol
(`docs/rules/protocol.pdf`) and is registered in the lab as `d_<name>`. Nothing in `bot/` changed.

(Results sections are filled in below as the runs finish.)

## 1. The old Hold'em bots: which two were useful, and why

Evidence (`docs/reports/OPPS_ANALYSIS.md`, `logs/discard_holdem_tier2_vs_bots.txt`,
`logs/e7/full.txt`, `docs/reports/TIER2_DISCARD.md`): Tier 2 chips per hand and match score against each.

| Bot | Hold'em, locks off, 50 pairs | `discard_holdem` Phase E start, 16 pairs | E7, final bot, 50 pairs |
|---|---|---|---|
| opp1 | +4.40 ± 0.16 (0.98) | +6.25 ± 0.82 (0.94) | +7.69 ± 0.22 (0.99) |
| opp2 | +7.74 ± 0.26 (1.00) | +1.79 ± 0.48 (0.88) | +2.58 ± 0.19 (0.89) |
| **opp3** | **−2.73 ± 0.33 (0.15)** | **−0.53 ± 0.29 (0.19)** | +0.10 ± 0.07 (0.61) |
| **opp4** | +1.41 ± 0.15 (0.86) | **−2.05 ± 0.35 (0.25)** | **−0.60 ± 0.17 (0.38)** |

The numbers confirm the expected pair: **opp3 and opp4** are the only bots that beat or tie Tier 2 on
`discard_holdem`; opp1 and opp2 lose by +2 to +8 chips per hand in every run. Kept and converted:

- **opp3** (`Opps/discard/conv_opp3`). Useful: a real bluffing and iso-raise game (63 % flop bets, 52 %
  big-blind iso-raises of limps), opponent stats that work (fold-to-bet, 3-bet, river bluff index), a
  preflop open range that moves with the opponent's fold-to-open and 3-bet rates, range narrowing
  after every action, a careful time-bank manager. Broken or odd: it was written for the MIT API (only
  the protocol layer changed), its "fold out when the match is won" lock is switched off in the lab, as
  before.
- **opp4** (`Opps/discard/conv_opp4`). Useful: bet size chosen by EV among 33 / 66 / 110 % pot and
  all-in, stack-stratified preflop charts, a pot-odds calling rule with street margins, river bluffs
  with blockers. Broken: its fold-to-bet stat counted every bet as "not a fold" and drifted to 0 (so it
  stopped bluffing), and it inferred opponent actions from pot growth. With the real protocol both
  come from the explicit `history`, so the stats work as the author intended. This makes the converted
  bot a little stronger than the old one.
- **opp1** (not kept). Equity against a random hand, fold-to-open and fold-to-c-bet never update, so its
  nit exploit never fires. **opp2** (not kept). Cannot start (`TOTAL_COMBOS` import error), no stat ever
  updates, and its "match won, just fold" check reads this hand's stacks.

## 2. Pool design

### Axes along which real submissions differ

1. **Style:** tight / loose, passive / aggressive, bluff frequency, 3-bet and 4-bet appetite, slow-play.
2. **Strength estimate:** equity against a random hand (the weak LLM pattern), Monte Carlo against a
   tracked range, hand-class rules with no simulation, fixed charts.
3. **Discard:** lowest card, rule of thumb, sampled equity of the three keeps, use of the opponent's
   revealed discard or not.
4. **Sizing:** fixed fractions, minimum raises, EV-chosen, pot-geometry / polarised.
5. **Adaptation:** none, simple stats, range narrowing, explicit exploit modes.
6. **Engineering:** careful time management against burning the bank.

### What the two converted bots cover

`conv_opp3`: balanced-aggressive, range-tracking Monte Carlo, sampled discard that reads the opponent's
discard, equity-based sizes, stat-driven bluffing, careful clock. `conv_opp4`: chart-based and fairly
tight preflop, EV-chosen sizes, a crude weighted range, Bayesian fold stats, hard deadlines. Between
them: range-narrowing MC, EV sizing, simple stats. Not covered: equity against a random hand, no-equity
rule bots, extreme aggression, trapping, explicit exploit modes, minimum-raise play, polarised
pot-geometry sizing.

### The seven new bots (each written by a fresh sub-agent)

Each sub-agent saw only `rulebook.pdf`, `protocol.pdf`, the verbatim prompt (stored in
`lab/opps/discard_pool.json`) and a one-line style brief. It did not read `bot/`, `lab/`, `logs/`,
`docs/reports/`, `Opps/` or anything about Tier 2. The bots are kept as delivered; their weaknesses
are the point of a realistic field. No bot needed a fix to finish a match.

| Bot | Style | Axis it adds |
|---|---|---|
| `conv_opp3` | balanced-aggressive, bluffs, iso-raises | range-tracking MC, stats-driven bluffing, careful clock (converted) |
| `conv_opp4` | chart preflop, EV-sized bets | EV sizing, Bayesian fold stats, hard deadlines (converted) |
| `new_eqrandom` | value-only, never bluffs | **equity against a random hand** + pot odds, fixed sizes, no adaptation |
| `new_rules` | moderately loose, fixed sizes | **no simulation at all**: hand-class and texture rules, heuristic discard |
| `new_lag` | loose-aggressive: ~90 % button opens, light 3- and 4-bets, 60 to 100 % pot | **extreme aggression and bluff frequency** |
| `new_trapper` | tight-passive, slow-plays, check-raises, calls down | **trapping and call-downs**, almost no bluffs |
| `new_exploiter` | solid default, then nit / station / maniac exploit modes | **explicit opponent classification** and a learned model of the opponent's discard |
| `new_minraise` | small-ball: min-raises, 25 to 35 % pot bets | **minimum-raise sizing**, cheap rules, wide calling of small bets |
| `new_geometric` | polarised big bets, MDF defence, stack-in-by-river sizes | **pot-geometry sizing and bluff ratios** from theory |

### Corners left out on purpose

- **A bot that burns its time bank or crashes** is realistic, but it gives no information about how
  Tier 2 should play: the match is a forfeit win. The health check reports any such bot; none of
  the nine would forfeit.
- **Always-raise / shove, calling station, random, pure nit:** already in the sparring pool
  (`all_in`, `maniac`, `calling_station`, `random_legal`, `tight`), so no new bot.
- The sparring bots and the organisers' starter play the discard at random or by lowest card; the
  pool's nine all use a real discard decision, so the discard axis is covered inside the pool.
