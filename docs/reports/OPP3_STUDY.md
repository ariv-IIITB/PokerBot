# OPP3 study: why `d_conv_opp3` beats Tier 3 (O3, 2026-11-04)

Light study (seeds 71000+). Evidence: S0 recordings (`logs/records/s0_9000/`, 9,600 hands per bot, both hole
cards known on every hand), three 30-pair runs vs `d_conv_opp3` (`logs/o3/`), and the source in `Opps/opp3/`
(ideas only; nothing copied). Laptop load average was 10–21 (shared with PD/DC/RD), so all numbers are
chips/hand with SE over pairs; wall-clock-budgeted brains are slightly noisy.

## What it is
An LLM-written equity bot: equity vs a **Bayesian-narrowed range** (every action of ours reweights its 1,326
combos), pot-odds calls with a small margin, value bets **sized by its equity** (0.40 / 0.55 / 0.75 / 1.0 pot
for equity < .66 / .75 / .85 / above), bluff frequency **scaled by our measured fold-to-bet** (`0.30 + (ftb − 0.40)`,
so it bluffs more against folders), a "lead is safe, stop risking" fold-out, a time-bank governor. It never
sees our cards; it discards the lowest card 63 % of the time (same as the rest of the pool).
Profile (S0): VPIP 83 %, PFR 35 %; bets 61 / 50 / 48 % of unfaced flops / turns / rivers; folds to our bets
42 / 67 / 70 %; raises our bets 1–9 %; WTSD 21 %.

## Where it beats us (Tier 3 −1.75 ± 0.35, tier3x −1.26 ± 0.23, 30 pairs, locks off)
Accounting, Tier 3, chips/hand: opp folds +4.4 (pre .39, flop .58, turn 1.5, river 1.9) against **we_fold −3.2**
(flop −.79, turn −1.28, river −1.16) and **river showdowns −2.8** (lose 2,015 pots at −76 each, win 1,951 at +44).

* **Our folds are right.** With both hands known: when we fold to its bet we are ahead 8 % (flop/turn) and
  19 % (river); calling would have lost on every size bucket. Nothing to fix there.
* **Size tells strength, and we ignore it.** Its unfaced bets, share with hand < 0.5 vs random (weak) by bet / pot:
  flop .4–.75: 24 %, ≥ .75: 0 %; turn .4–.75: 28 %, ≥ .75: 3 %; river .4–.75: 46 %, .75–1.1: 18 %, > 1.1: 6 %.
  **Our river calls vs ≥ .75 pot bets win 31 % (.75–1.1) and 12 % (> 1.1)**, true EV −16 / −75 chips per call;
  calls vs .4–.75 pot bets win 64 % and are +22 per call. Tier 3's river call rule is `eq ≥ pot odds + 0.02 +
  0.1·bet/pot`, with `eq` blind to what the bet says about the range (no bet-conditioned narrowing; the shipped
  bluff-index ignores size). Replaying the river-call decisions of all 6 pool bots (both hands known): a rule
  using the bettor's range slice instead gains +0.1 to +1.3 chips/hand per bot in-sample (below).
* **Its own bluffs are cheap for it:** we fold 34 / 46 / 68 % to flop / turn / river bets, so its `ftb` rule
  bluffs more; its river bets ≤ 1.1 pot are 18–46 % weak.
* **We under-bluff the over-folder:** Tier 3 bets weak river hands (equity < .5) 3–8 % of the time while it
  folds 60–75 % to river bets of .4–1.1 pot (break-even is 30–45 %); turn 31–36 %, fold 61–72 %. The exploit
  layer moves this only a little (river checked-to bet rate 40 → 43 %).
* Not the discard: kept-hand strength at the river is equal (ours .649, its .608 on shared hands; both lose
  .04 to hindsight). Not preflop: its folds and ours net about +0.3.

## The family (recognisable from play, no name needed)
Loose-aggressive preflop (VPIP ~80 %, PFR 35 %), bets 50–60 % of unfaced flops/turns/rivers, **folds 40–70 % to
our flop/turn/river bets**, rarely raises them, **bet size rises with hand strength** (large bets almost never
weak), wins by value-betting big when we have a bluff-catcher. Also true of `d_new_rules` and `d_new_exploiter`
(over-folders with value-only river bets); the trapper/minraise are the same shape with fewer bets.
Observable online: X1 over-folder verdict, river-bet rate, bluff index, the size distribution of faced bets.

## The same two leaks in `d_new_exploiter` (−2.06 S0) and `d_new_rules` (−0.90 S0)
Different code, same shape (S0 recordings, 9,600 hands each): their river bets are value-only (weak share 0–6 % at every
size), they fold to our bets (exploiter 83 % to .75–1.1 pot river bets, 85 % to .4–.75 turn bets, 96 % on the turn when
we hold air; rules 61–63 %), and the chips go into **river showdowns** (exploiter −3.18, rules −1.39, conv_opp3 −2.8
chips/hand) while we bet weak turns 11–24 % and weak rivers 0–17 %. So the shared weakness is: **we pay off value bets
and under-bluff folders**. River call EV vs their bets .4–1.1 pot: win 0–18 %, −15 to −37 per call.

## Candidates (all adaptive; both flags off by default; seeds 71000+, 30 pairs, locks off, vs conv_opp3)
1. **`x_narrow`: bet-range narrowing on river calls.** Re-read our equity against the bettor's top slice:
   slice = `f·(λ + (1−λ)·F)·(1−b)`, f = their river-bet rate, b = bluff index, F = share of their faced river bets
   at least this large (own size distribution, prior 0.5 worth 8 bets), `λ = 0.4`; bluffs count as beaten by
   anything above their 40th percentile; Tier 2's flat big-bet penalty dropped. No bot named. Offline replay on
   6 pool bots (chips/hand, in-sample): conv_opp3 −0.45 → +0.12, exploiter −1.14 → +0.06, rules −0.41 → +0.58,
   trapper −0.18 → +1.37, minraise +0.21 → +0.65, lag +6.04 → +7.64. Measured vs conv_opp3: tier3 −1.75 ± 0.35,
   tier3x −1.26 ± 0.23, **+ x_narrow −0.68 ± 0.15** (+0.58 ± 0.27, z +2.1). River vs-bet: call 34 → 9 %, fold 55 → 88 %.
2. **`x_air_eq` (0.45): river bluff pool vs a verdict over-folder.** `river_air_eq` grows from .18 toward .45 by the X1
   confidence, so weak hands bet the river (checked-to bet rate 43 → 52 %; its river folds +2.08 chips/hand).
   With 1: **+0.18 ± 0.17, match score 0.650 ± 0.062** (+0.86 ± 0.23 vs candidate 1 alone, z +3.8).
   Total vs tier3: +1.9 chips/hand, from a loss to a small win (30 pairs, same seeds, load ~20).
3. **`x_stab`: bluff weak hands when unfaced, at the rate the street's measured fold rate pays** (flop, turn, river;
   needs the over-folder verdict; chance = `lam·(fold − break-even)/0.5`). Built for the exploiter/rules/conv_opp3 turn
   shape; results in the handoff.
4. Not built: the same narrowing for turn/flop bets (+0.1–0.2 expected; those calls go through MDF in `tier3.py`,
   not `choose`), and size-aware flop/turn bluffing (it folds 58–78 % to .4–.75 pot bets). Held-out bots not run.
Pool and simple-bot guard results: `docs/tier4/handoff/O3.md`.
