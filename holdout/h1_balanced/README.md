# h1_balanced — theory-minded balanced Discard Hold'em bot
Style: pot-geometry sizes (~1/3, 2/3, pot), bluff share s/(1+2s), MDF-aware calls, position-aware realisation.
Evaluator: own best-5-of-5..7 (table lookup, verified vs brute force on 18k random hands).
Preflop: Chen-like 3-card score -> percentile; SB opens top ~70% (5-6), BB 3-bets value + near-threshold bluffs, MDF-based defence.
Postflop: Monte-Carlo equity vs an opponent range weighted by each of its actions (size-based value/bluff split, call=MDF band, check=capped).
Revealed opponent discard down-weights kept pairs that contradict it; discard = max MC equity of the 3 keeps vs the weighted range.
Bet/raise choice from equity tiers + draw semi-bluffs + air bluffs at s/(1+2s) frequency; all-in when commitment is high.
Safety: try/except fallback to a legal action, sanitised replies, stdout = protocol only, sample counts scale with time bank.
Tests (lab engine, 20 seeds x 200 hands, 30 s bank): vs starter +13.6 chips/hand (54,479 total), 0 forfeits, 0 illegal;
self-play ~0 (mean -0.12/hand, mixed play: raises ~25%, folds ~25%); mean reply ~4 ms, worst ~63 ms.
Debug: H1_DEBUG=1 logs reply kinds to stderr.
