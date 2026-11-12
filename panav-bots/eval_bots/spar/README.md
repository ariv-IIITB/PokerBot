# Sparring bots

Ten quick rule-based bots (no CFR training) for 1v1 tests. Standard library only; every reply is legal, each
decision takes under 20 ms, stdout carries protocol replies only.

| bot | style |
|---|---|
| `eqtag` | solid baseline: equity thresholds, calls when equity beats the pot odds, bets 2/3 pot |
| `trapper` | slowplays strong hands on flop and turn, check-raises the river, folds weak hands to big bets |
| `potctl` | small bets with medium hands, pot-size bets with strong ones, folds medium hands to bets over 3/4 pot |
| `polar` | bets 2x pot with its top and bottom 15% of hands, checks or calls the rest |
| `betfold` | v6-like: bets or raises about 60% postflop, almost never calls, folds about 70% when bet into |
| `light3b` | 3-bets 40% preflop, continuation-bets every flop, gives up on the turn without equity |
| `donk` | leads into the preflop raiser on every street with any pair or draw |
| `adapt` | simple exploiter: opponent folds over 50% to its bets: bluffs twice as often; calls over 60%: no bluffs, thinner value; re-checks every 20 hands |
| `tilt` | tight; after losing a pot over 80 chips plays loose-aggressive for 30 hands |
| `discardread` | reads our exposed discard (a high card thrown suggests a pair or suited cards kept) and bluffs more when the board misses that guess |

`common.py` holds everything shared, so a bot file is only its style:
- the protocol loop, legal-reply helpers (every reply legal), an RNG seeded from `os.urandom`;
- an evaluator written for this repo (agrees with `shared/evaluator.py` on 20,000 random pairs of hands);
- preflop: a table of all 1,755 distinct 3-card starting hands (equity against a random 3-card hand, both keeping
  the best pair, 5,000 deals each) and percentile-based open / defend / 3-bet / 4-bet rules;
- postflop: Monte Carlo equity against the opponent's likely range (samples weighted by strength raised to a
  pressure from what they bet, raised or called, scaled by how often they bet, and by whether keeping their pair
  fits the card they threw), pot odds with a realisation factor, value bets by street, c-bets, semi-bluffs;
- learning inside a leg: after every showdown it scores the hands the opponent bet with on the turn and river,
  by bet size, and reads their next bet through that; plus fold / call / bet / preflop-raise counters;
- a discard picked by equity (the same random runouts for all three choices).
A decision takes a few ms (worst seen 7 ms in 25,000 random requests).

## How strong they are (Stage 1, 20 matches per row, 12 Nov)

Against v16 (a strong equity + CFR-table bot), mean chips per hand over the 10 bots: first version -7.40, shared
core rebuilt -1.51, with showdown learning **-0.99** (potctl +0.17, 14-6 in matches). The final bot (`dist/bot.py`)
beats the 10 current bots 134-66 in matches (it beat the first versions 191-9).

## Play any two bots

```
python eval/bots/spar/play.py trapper polar --matches 20 --workers 4
python eval/bots/spar/play.py final eqtag --matches 10 --stage 2
python eval/bots/spar/play.py ~/path/to/any_bot.py donk
```

`BOT` is a name from the table, `final` (= `dist/bot.py`), or a path to a bot file. A match is two legs with the
same deals and the seats swapped. Output: every match, wins / draws / losses, chips per hand with a 95% interval.
At most 4 matches at a time.

## Checks

```
python eval/bots/spar/smoke.py            # Stage 1 and Stage 2 on the official engine, vs eqtag and vs itself
```
