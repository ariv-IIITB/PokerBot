# h5_smallball: position-driven small-ball (Discard Hold'em)
1. Style: uses last-to-act postflop, small frequent bets (25-40% pot), probes/delayed c-bets, floats, small pots OOP.
2. Single `bot.py`, stdlib only, own 7-card evaluator (~6 us/eval), JSON lines, stderr debug only.
3. Preflop: Chen-style score over the best 2 of 3 cards + flexibility bonus; wide small opens (4-5), wide BB defence, 3x 3-bets.
4. Flop equity: Monte Carlo where the opponent keeps its best 2 of 3; discard = best keep by MC equity plus a small draw bonus (larger in position).
5. Turn/river: MC vs the opponent's unseen kept cards, softly weighted by its revealed discard.
6. Facing bets: pot odds, shrunk equity vs bet size/raises, extra margin vs big pressure out of position; flop/turn floats in position with draws.
7. Checked to: IP bets value, probes and stabs (more after a float or a check-check street); OOP bets value only, probes after weakness, rare slowplay.
8. Opponent model: fold-to-bet and aggression rates nudge bluff frequency and shrink.
9. Safety: try/except around every decision, final legality clamp, sample counts scale with time_left_ms.
10. Test (20 duplicate pairs x 200 hands): +3.88 chips/hand vs starter, 0 errors/forfeits, worst reply 39 ms; self-play 4 pairs +0.24 (about even, no errors).
