# Seed ledger (league track)
| range | purpose | bots |
|---|---|---|
| 1900-1902 | EX1 smoke test of pipeline (not used for selection) | corners + 1 random vs final |
| 1000-1999 | EX1 search: r0 = 1000-1007, then r1..r4 = next 8-blocks (1008-1039) | param bots vs final, 200 hands |
| 2000-2099 | EX1 confirmation (24 pairs x 200h; 8 pairs x 500h) | top configs vs final |
| 3000+ | RESERVED random-config holdout, do not use | - |
| 2000-2023 | EX1 confirmation W1-W4 vs final/bot.py, 24 pairs x 200h | W1..W4 |
| 2050-2057 | EX1 confirmation 8 pairs x 500h | W1..W4 |
| 2060-2067 | EX1 zoo check (W1 vs 5 bots) + behaviour logs (final vs lakshya1, final vs W1) | diagnostics |
(search actually used 1000-1023: r0 1000-1007, r1 1008-1015, r2 1016-1023; opponent = loop/evalbuilds/final_seeded.py)
