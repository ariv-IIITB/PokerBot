# h3_adaptive: opponent-modelling exploiter (Discard Hold'em)
- Style: sound equity baseline that shifts toward exploitation as the opponent sample grows.
- Equity: Monte-Carlo with its own 7-card evaluator, discard-aware (both sides keep the best 2 of 3 on the flop).
- Discard: picks the card whose removal maximises MC equity vs a sensible opponent discard.
- Opponent model (decayed 0.985/hand, with priors): fold-to-bet/raise, bet rate by street, preflop raise/fold,
  showdown strength (percentile) of its bets and calls, and how often it discards its highest card.
- Exploits: bluffs more vs folders, value-bets thinner vs callers, weights the opponent's range by
  percentile^k (k from its bets' showdown strength and bet size) so it folds to tight bettors and calls frequent bluffers,
  semi-bluff raises with draws vs frequent bettors.
- Safety: all decisions wrapped, legal replies enforced, sample count adapts to the time bank (<= 16 ms/decision).
- Test (20 duplicate pairs x 200 hands, discard_holdem, pokerbots protocol): vs starter +10.85 ± 0.27 chips/hand,
  match score 1.000 (40/40); vs itself -0.09 ± 0.26 (0.475). 0 forfeits, 0 illegal replies, worst reply 0.09 s.
