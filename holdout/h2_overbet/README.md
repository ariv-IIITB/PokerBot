# h2_overbet — high-pressure aggressor (Discard Hold'em)
Style: opens wide on the button, 3-bets light in the BB, bets most flops, overbets 1.0-2.0x pot
with a polarised range (value + draws/blockers), fires multiple barrels, gives up on missed rivers,
folds marginal hands to raises but re-raises strong draws (flush / open-ended).
Decisions: own 5-of-7 evaluator (checked vs brute force), Monte Carlo equity vs a random range
(80-140 samples, fewer if the bank is tight), equity shrunk by bet size when facing aggression,
bluff frequency scaled by the opponent's observed fold rate. Discard = equity of each kept pair
(common random numbers). Wrapped in try/except; all replies validated and clamped.
Tests (20 duplicate-style seeds x 200 hands, real protocol, audit on): vs starter +138,756 chips
(+34.7/hand, won 20/20, no forfeit, 0 illegal); vs itself +1,637 (balanced, 0 errors).
Timing: ~2 s of the 30 s bank per 200 hands (~2 ms mean); worst reply ~30 ms.
