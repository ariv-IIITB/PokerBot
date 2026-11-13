# h4_trapper (Discard Hold'em, single-file bot.py, stdlib only)
Style: tight, patient, check-raise heavy trapper.
- Preflop: opens a narrow strong range (equity >= .545 vs random, via Monte Carlo with hindsight keep), rare light opens; 3-bets strong hands (some flats to trap), calls by pot odds + margin.
- Flop/turn: with a very strong hand (equity >= .86) checks ~62% to induce, then check-raises; bets 60-80% pot with strong hands; raises c-bets with strong made hands and big draws (semi-bluff ~30%).
- Medium hands: check, and call down only if equity > pot odds + margin; the margin shrinks against an aggressive opponent (observed postflop aggression frequency).
- River: big value bets (0.8-1.25 pot) with the goods, rare bluffs (8%) only vs opponents that fold often.
- Equity: Monte Carlo (130-220 samples, own 7-card evaluator) over opponent hands, reweighted by the opponent's actions this hand (bet size, aggression, calls, checks); samples cached per street.
- Discard: highest equity among the 3 keeps vs the narrowed range.
- Safety: all decisions in try/except -> legal passive fallback; raises clamped to min/max; debug to stderr only.
- Test (lab, pokerbots protocol, 20 matches x 200 hands): vs starter +5.06 chips/hand, 20/20 match wins; self-play -0.15 (11/20); 0 forfeits, 0 illegal replies; mean reply ~3 ms, worst 34 ms.
