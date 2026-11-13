# VAL1: is final's check/call with strong hands a leak? (13 Nov 2026)
**Verdict: FAIL. Do not ship `valuebet`. The check-back and the call are not a measurable leak; D1's +12 to +20 chip gap was selection.**

## 1. Where final decides
Blueprint table row (`botsrc.policy.decide_action`) -> `hooks.exploit_adjust` -> `botsrc.exploit.adjust` (flop/turn, source "blueprint" only).
River goes through `river_special` / the river solver and is not touched by `adjust`. Existing moves: `station` (thinner value bets, pct .55-.80, gated on the
river-call trait; river calls only, so slow to fire) and `rivervalue` (changes the solver's opponent range facing a big bet, i.e. call/fold, not bet/check).
Neither shifts check->bet or call->raise for the top hands, which is what D1 asked about.

## 2. Method
CF1's replay (`cf_replay.py`) handles fold/call/check-behind classes only and restarts both bots each replay (no in-match learning). It was not extended;
instead the **full-match A/B of the policy itself**, which includes the opponent's real reaction. Move `valuebet` added to `botsrc.exploit`
(`panav-bots/loop/val1/src/botsrc.exploit.py`): strong bucket (S1 percentile >= .75), flop/turn, check mass -> bet (sizeA if the node has none: `vb_force`),
call mass -> raise; gate = new trait `caller` (opp calls/raises facing our bet, SPRT .55 vs .75, pooled flop/turn/river). Experiment builds ungate it (`vb_gate=off`).
Dev bots (lakshya1, geometric, exploiter, conv_opp3, eqrandom, minraise, potctl), 24 pairs x 200h each, seeds 11000-11023, paired by seed. Pooled over 168 pairs:
| variant (strong buckets, flop+turn) | pooled delta c/h +- SE | note |
|---|---|---|
| ungated, all check mass -> bet (existing bet slots only) | +0.026 +- 0.075 | no effect |
| ungated, forced small bet on pure-check nodes | +0.063 +- 0.081 | no effect |
| ungated, all call mass -> raise (TV cap .3) | **-0.270 +- 0.096** | loses to eqrandom -1.06, exploiter -1.03 (z -4.5, -4.8); they raise back |
| gated cand (`caller` trait, bet share .6, no raise) | +0.051 +- 0.070 | minraise +0.39, exploiter -0.32 |
So the true value of betting instead of checking with eq>=.8 is about zero (+-0.08 c/h); raising instead of calling is clearly negative. The only positive
cells are the calling-station-like bots (minraise +0.26 to +0.39), as the hypothesis said, but too small to be shipped.

## 3. Pre-registered check (the PASS rule in the task, unchanged)
Validation bots disjoint from dev, seeds 12000+, 40 pairs x 200h, base vs cand. **Stopped after 8 of 16 planned bots** because a clause had already failed
(no bot down > 2 SE) and the pooled delta was negative; more bots could not rescue the verdict.
adapt -0.23+-0.16, betfold -0.01+-0.21, discardread -0.01+-0.14, **donk -0.44+-0.16 (z -2.7)**, light3b -0.27+-0.22, polar -0.40+-0.26, tilt -0.05+-0.19, trapper +0.06+-0.22.
**Pooled -0.170 +- 0.071 (z -2.4, 320 pairs); match score sum base 183.5, cand 176.2.** Needed: >= +0.10 and >= 1.5 SE. FAIL on mean, wins, per-bot clause.
Data-loss note: my own `rm` wiped the validation JSONs (pair level) before they were committed; the table above is the printed `compare.py` output. Rerunning is cheap.
Not run (moot after FAIL): lakshya1 500h leg, Stage 2 (500h) legs, head-to-head cand vs base, timing/legality build `final_valuebet.py`. Stage 1 only was measured.

## 4. Exploit-back, `adversaries/trapper2.py` (check-raises strong hands, 40 pairs x 200h, seeds 15000)
base +3.39 +- 0.37 c/h, cand +3.19: delta -0.21 +- 0.24 (n.s.). Final already beats this trapper heavily; the cand's cost is small but the "pooled gain" is negative, so the clause fails too.

## 5. Phil Ivey test
"Against a station I bet my strong hands because they pay; against someone who check-raises or raises back I do not, and I do not fire into a trap
more often just because the line looks greedy. A solid solver-style player checks strong hands on some boards to protect its checking range; the checking
range is what lets it call and raise later. Raising for value over a bet is where it hurts: the opponent's bet already has strong hands in it." Verdict:
bet-up against a measured caller = SITUATIONAL (small, only behind the gate; not worth shipping at +0.05 +- 0.07); call->raise = OVERFIT/negative; the D1
hypothesis is mostly selection (hands the blueprint bets are different hands from the ones it checks). The check-back is the blueprint balancing.

## 6. Files (branch loop/val1)
`val1/src/botsrc.exploit.py` (move, off by default; not in `config exploit`), `val1/build.py`, `runset.sh`, `compare.py`, `unit_vb.py` (move unit test, passes),
`adversaries/trapper2.py`, `results/val1/dev/*` (dev pair data).
