# Official rules: summary

Source of truth: [rulebook.pdf](rulebook.pdf) and [protocol.pdf](protocol.pdf), both
received 2026-10-28, and [problem_statement.pdf](problem_statement.pdf), released 1 Nov 2026
(game rules with worked examples; it changes no rule above, checked 2 Nov). Where it conflicts with
the Rulebook on the *game rules* (Rulebook section 4), the Problem Statement wins; on everything
else the Rulebook wins (Rulebook 1.3, PS section 10).
Values marked *(prov.)* are provisional and may change before the deadline.

**Deadline: 15 Nov 2026, 23:59 IST.** One final bot per team, uploaded on Unstop.

## Game: Discard Hold'em (Rulebook 4, Protocol 4 and 7)

- Heads-up no-limit. Blinds 1/2. Stacks 200 each, reset every hand.
- The button posts the SB, acts first preflop and last postflop. Seats alternate every hand.
- 3 hole cards each. Preflop betting, then a 3-card flop, then flop betting.
- **Discard:** if nobody folded, both players discard exactly 1 hole card *simultaneously*.
  Both discards are then shown to both players and **removed from play** (not added to the board).
  The discard also happens when a player is all-in (the remaining board is dealt, and the discard
  still comes after the flop).
- Turn (1 card), turn betting, river (1 card), river betting, showdown.
- Showdown: the best 5-card hand from the 2 remaining hole cards plus the 5 board cards, standard
  rankings. **Confirmed (PS section 6): any 5 of the 7 count, using both, one or none of the hole
  cards** (a player can "play the board"; a split pot is net 0 each).
- Minimum raise-to = `opp_bet + max(last bet/raise size this street, 2)`. With no bet yet the
  minimum is 2. The BB counts as the first raise preflop, so the first preflop minimum is 4.
- Maximum raise = all-in, meaning the most either player can commit this street. If that is below
  the minimum, only the all-in amount is legal.
- **At most 4 bets/raises per street; preflop the BB counts as the first** (so 3 voluntary raises).
- Illegal action or unparsable reply: check if legal, else fold (a `notice` is sent).
- Illegal, missing or unparsable discard: the lowest-ranked hole card is discarded (2 lowest, A
  highest). On equal ranks the first suit in the order s, h, d, c goes.

## Bot limits (Rulebook 5, Protocol 8)

- Python 3.11, standard library + numpy + scipy only. No installs at runtime.
- 1 vCPU, 1 GB RAM *(prov.)*. No network. Read-only filesystem.
- A bot may read files inside its own submission; it may not write files, open sockets or start
  other processes.
- **Two legs per match, each a fresh bot process** (no state crosses legs): leg 1 plays every deal
  once, leg 2 replays the same deals with hole cards and seats swapped. Time bank per leg, not
  reset between hands: **30 s / 200 hands (Stage 1 leg)** and **75 s / 500 hands (Stage 2 leg)**
  *(prov.)*. Time is charged from when a request is sent until the reply line arrives, for both
  action and discard requests.
- Any single reply must arrive within **5 s** *(prov.)*.
- Wall-clock kill per leg: **90 s (Stage 1)** and **225 s (Stage 2)** *(prov.)*.
- Start-up: 5 s from launch to ready for `init`, per leg. **Not charged** to the bank.
- Crash, exhausted bank, a reply over 5 s, or the wall-clock kill all **forfeit the whole match**
  (the other leg is not played): a loss, and the opponent gets Δ = +C.
- stdout carries protocol JSON only, flushed after each message. stderr is for debugging only,
  capped at 64 KB per match and never parsed.
- No state is kept between legs (the bot starts fresh each leg). Randomness is allowed.
- Submission: one `bot.py`, or a `.zip` with `bot.py` at the top level, **≤ 5 MB**. Run as
  `python3.11 bot.py`.

## Tournament and scoring (Rulebook 7–9)

- Every deal is played twice with the cards swapped between seats (duplicate). The bot is not told
  which deals are pairs.
- **Stage 1:** Swiss, 6 rounds (7–8 if more than ~1000 teams). Each match is 200 duplicate deals
  (400 hands). With fewer than ~64 bots it is a round robin instead; with 32 or fewer it is skipped.
- **Stage 2:** the top 32 play a full round robin of 500 duplicate deals (~1000 hands) per match.
  Scores reset. Stage 2 alone decides the prizes (Rs. 20k / 14k / 8k).
- A match is won by the bot with more net chips (equal = draw). Points: win 1, draw 0.5, loss 0.
- Tie-break: capped chips per hand = Σ clip(Δm, −C, C) / Σ Hm, with **C = 400 (Stage 1) and
  1000 (Stage 2)** *(prov.)*. Still level: a replay match.
- A forfeit is a loss, and the opponent's Δ = +C. If both forfeit in the same hand, it's a draw with Δ = 0.

## Conduct (Rulebook 10)

- The code must be our own. Copying from other teams or public bot repos is prohibited; standard
  libraries and published algorithms are fine. Prize winners' code is reviewed, and the organisers
  may run similarity checks. **Never copy code from `Opps/` into `bot/`** (ideas only).
- Exploiting the engine or evaluation system is prohibited and must be reported. Exploiting other
  bots' play is fine.

## Protocol (Protocol 2–7): see protocol.pdf for field tables

- JSON lines, UTF-8, each with a `"type"`. Ignore unknown types and fields. Reply only to
  `action_request` and `discard_request`; a reply with no request outstanding is ignored.
- Cards look like `As`, `Td`, `2c`. Seats are `button` and `big_blind`. Streets are `preflop`,
  `flop`, `turn` and `river`. Call and raise amounts are **"to" amounts** (total committed this street).
- Engine → bot: `init`, `new_hand`, `action_request`, `discard_request`, `discard_result`,
  `hand_result`, `notice`, `match_end` (then exit).
- Bot → engine: `{"type":"action","action":"raise","amount":40}` and
  `{"type":"discard","card":"Kd"}`.
- Opponent actions arrive only in `history` (all voluntary actions this hand, oldest first).
- Worked example: Protocol section 10 (bot on the button, net +12).

## Still open

- Final values of the provisional limits: RAM, time banks, per-reply limit, wall-clock kill and C.
- The organisers' starter kit and its local match runner (PS section 9 tells teams to use it; we
  don't have it). Our stand-in is `lab/sparring/starter_bot.py`.

The worked examples (PS section 8) are tests in `tests/test_problem_statement.py`.
