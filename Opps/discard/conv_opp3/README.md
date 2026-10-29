# conv_opp3: `Opps/opp3` converted to Discard Hold'em (Phase F v2)

Same bot, same style (equity vs a modelled range, range narrowing after every action, bluff
frequencies from measured fold rates, iso-raises, a time-bank manager). `pb/` is the original core
with these changes; `bot.py` is the new protocol layer (JSON lines, `docs/rules/protocol.pdf`).

- **3 then 2 hole cards.** A 3-card hand is valued as its best 2-card keep: preflop percentile of the
  best keep among best keeps of random 3-card hands (`pb/ranges.py`), equity = best keep scored on
  shared samples, picked on one half and measured on the other (`pb/equity.py`).
- **Real discard decision** (`Brain.discard`): sampled equity of each keep against the opponent's range
  on the flop; a no-simulation fallback in panic mode.
- **Opponent's revealed discard** (`RangeTracker.apply_discard`): both discards are dead cards (never
  on the board, never in the opponent's hand); combos that would have kept the discarded card
  instead are down-weighted. The opponent range starts from the distribution of best keeps.
- Time: budgets from `time_bank_ms` / `total_hands` / `time_left_ms`, fewer samples (3 keeps cost 3x).
- `fold_out` (stop risking chips once the match is mathematically won) is **off** by default, as in
  the lab's earlier opp3 setup (`lab.eval.OPP_CONFIG`), so locks-off runs measure chips.
- Not changed: strategy thresholds, sizing, bluff logic, stats.
