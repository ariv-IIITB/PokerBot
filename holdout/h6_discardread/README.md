# h6_discardread — information-driven Discard Hold'em bot
1. Style: reads what the opponent kept. Its revealed discard + flop board + betting give a weighted posterior over its kept pair.
2. Posterior: sampled kept pairs from unseen cards; weight = discard-consistency (kept pair should beat the alternatives with the discard, or discard = lowest card; mix learned from showdowns) x betting likelihood (bet/raise/call/check vs a hand-strength proxy, bet-size aware, trust learned from showdowns).
3. Own discard: sampled equity of each of the 3 options vs 3-card opponent hands (common random numbers), small concealment tie-break.
4. Postflop: equity vs posterior; value bets ~60-78% pot, thin value 33-45%, call vs pot odds + margin, raises for value, semi-bluffs.
5. Bluffs only when the posterior says fold-equity is high (few draws / weak range); no bluffs vs calling stations (call rate > 68%).
6. Preflop: linear equity model of the 3-card hand (fit offline by rollouts, R2 0.78) -> open/limp/3-bet/call by pot odds, opponent raise frequency shrinks our equity.
7. Own evaluator (best 5 of up to 7, verified vs brute force); stdlib only; every path wrapped, passive legal fallback; stdout protocol only.
8. Time: mean ~5 ms/reply, worst ~13 ms (budget adapts to remaining bank).
9. Tests, 20 pairs x 200 hands: vs starter +11.96 +/- 0.35 chips/hand, match score 1.000 (40/40), 0 errors/forfeits.
10. Self-play (20 pairs): +0.49 +/- 0.34 chips/hand (even, as expected), 0 errors/forfeits.
