# call1 v3 PRE-REGISTRATION (before any v3 run)
Move: v2's band (call of a >= .70-pot bet, not all-in, our S1 proxy in [.70, .85), p = .75, ledger, aggressor/riverbluff gate) but the
gate is the opponent's BIG-BET FREQUENCY, observable every hand: bigs/opps = share of their postflop bet opportunities (no bet of ours to face)
answered with a bet >= .70 pot (pot rebuilt from the hand history). w = 0 if opps < 12; w = 1 if freq <= 0.40; w = 0 if freq >= 0.55; linear
between; ramps in over 6 opportunities. (CF1: bluff-heavy opponents .82-.92, value-heavy .30-.32.) Thresholds frozen here.
Seeds: 20000-20029 dev (6 bots: new_eqrandom, lakshya1, new_exploiter, new_geometric, conv_opp3, potctl; base and cand paired);
validation (only if dev match wins cand >= base) 22 bots, 40 pairs, seeds 21000-21039; 500h lakshya1 / new_eqrandom 24 pairs seeds 22100 / 22200.
PASS (parent's PRIMARY METRIC): pooled match-win rate cand - base >= +2.0 pp, pooled chips >= 0, no bot's win rate down > 2 SE, lakshya1 500h wins not lower,
head-to-head cand >= 50% of matches (40 pairs, seeds 23000-23039), potbluffer loss < gain (seeds 23100-23139), timing within 5 ms.
