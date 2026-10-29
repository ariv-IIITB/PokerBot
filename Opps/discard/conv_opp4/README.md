# conv_opp4: `Opps/opp4` ("Titan") converted to Discard Hold'em (Phase F v2)

Same style: stack-stratified preflop charts, range-weighted Monte Carlo equity (256 / 384 / 512 samples,
exact river), calling rule = pot odds + street margins + sampling error, candidate sizes 33 / 66 / 110 %
pot and all-in picked by expected value, river bluffs with blockers, Bayesian fold-to-bet stats,
per-decision deadlines. `bot.py` holds the protocol layer and the decision flow.

- **3 then 2 hole cards.** Preflop charts are applied by frequency to the best keep (`keep3.py`,
  `preflop.hand_in_chart`): a hand is "in the chart" when its best keep is in the top share of hands the
  chart contains (same opening / defending frequencies as the original). Equity = best keep (`equity.py`).
- **Real discard decision** (`PokerBot.choose_discard`): equity of each keep vs the opponent's range on
  the flop, shared samples; heuristic fallback.
- **Opponent's revealed discard** (`OpponentModel.apply_discard`): both discards are dead cards; combos
  whose alternative keep (with the discarded card) would have been stronger on the flop get x0.2.
- **Opponent stats and range updates now come from the request `history`.** The original inferred
  actions from pot growth and recorded every bet as "not a fold", so its fold-to-bet stat drifted to 0;
  with the real protocol the fold / call / raise answers are explicit, so the stats work as intended.
- Time: the per-decision cap went from 35 ms to 20 ms (about 5 decisions per hand with the discard).
