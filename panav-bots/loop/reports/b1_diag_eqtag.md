# B1 DIAG: final (A) vs spar/eqtag (B)
Run: 30 pairs x 200 hands (12000 hands), real protocol, no forfeits (A/B 0/0), full 30 seeds (no reduction).
**Headline: +0.63 +- 0.23 chips/hand (about 2.7 SE), match score 0.633.** Final is winning. The by-seat split
is +0.43 on the button and +0.83 in the big blind, so no seat-specific leak.

## Chips by ending (n, chips)
- showdown WIN 1339, +62753; showdown LOSS 696, -45667 (net +17k; split 109)
  - Showdown size split: stack-size pots (|net|>=150) won 185 / +36.8k vs lost 127 / -25.3k. Mid pots 137/+10.8k vs 147/-12.6k
    (a small negative). Small pots 1126/+15.2k vs 422/-7.8k.
- OPP folds: preflop 3298 +7104; flop 296 +1668; turn 826 +9521; river 649 +14395 (total +32.7k)
- WE fold: preflop 2138 -5125; flop 1547 -10844; turn 651 -13061; river 451 -13157 (total -42.2k, mostly sunk investment)

## Opponent profile (counts from logs)
- First-in bet rate: preflop 0.65, flop 0.69, turn 0.41, river 0.29. Loose-aggressive early, then it gives up.
- Facing OUR bet: preflop fold 0.39; flop fold 0.16 (call 0.81); turn fold 0.53; river fold 0.75.
- When it bets the river and we call (n=347) we win at showdown 39%; when we bet the river and are called (n=212) we win 56%.

## Leak candidates (none is a confirmed leak; only hypotheses)
1. **Flop: we fold 37% to its bets (n=1547, -10.8k sunk).** Opp bets 69% first-in on the flop, so its bet range is wide.
   When we do call, the opp showdown/pot result is fine (the call win rate is about 49%). Mechanism: we may over-fold to a bluffy
   wide bettor. I CANNOT show a counterfactual from the logs (no equity of folded hands), so EV is unproven.
   General? Yes if gated on "opp bet freq >> value density". Move: lower the flop fold threshold when opp's first-in bet rate is above about 0.6.
   Ivey: SITUATIONAL. A great player defends wider against a player who bets almost every flop, but a good opp that
   switches to value-heavy betting would punish it; keep it behind the SPRT gate. Lesson from the playbook (overbetdef) applies: marginal calls can lose.
2. **Opp over-folds to our turn (0.53) and river (0.75) bets.** We already collect +9.5k and +14.4k from these; whether MORE
   bluffing is +EV is untested (we do not know our bluff share). Move: raise river/turn bluff frequency when opp's fold-to-bet SPRT says
   fold rate > 0.6. n=1475 opp-folds, +23.9k. Ivey: PRINCIPLE (attack a player who gives up too often; the exploit-back risk is a
   value-heavy caller, which the gate detects within the leg). Probably already covered by final's exploit layer; check whether that move is on.
3. **Mid-size showdown pots (50-150): 147 losses -12.6k vs 137 wins +10.8k.** Slightly negative (-1.8k, about 0.15 chips/hand)
   and within noise. Not a leak; only watch it across the other four bots.

## Verdict
No real leak against eqtag: final is simply winning, and by 2.7 SE. The two numbers that look worst (showdown LOSS -45.7k, folds -42k)
are the natural cost of playing; showdown net is +17k and fold-to-bet loss is only sunk chips. I did not find a leak with n>=30, a
chip total, AND a counterfactual that gains chips. Candidates 1-2 need a cross-bot check (do they appear against the other B1 bots?)
before INTEGRATE touches anything. Method note: bet-size bucketing from `history.amount` is unreliable (cumulative vs
per-street), so I do not report size buckets.
