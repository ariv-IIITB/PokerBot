# Official rules: summary

Source of truth: [rulebook.pdf](rulebook.pdf) and [protocol.pdf](protocol.pdf), both
received 2026-10-28. The full **Problem Statement** (game rules with worked examples) is
released **1 Nov 2026**. Where it conflicts with the Rulebook on the *game rules* (Rulebook
section 4), the Problem Statement wins; on everything else the Rulebook wins (Rulebook 1.3).
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
  rankings. Our reading is that any 5 of the 7 count, as in Hold'em. To confirm on 1 Nov.
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
- **A bot may not read or write files, open sockets or start other processes.**
- Time bank per match, not reset between hands: **60 s / 400 hands (Stage 1)** and
  **150 s / ~1000 hands (Stage 2)** *(prov.)*. Time is charged from when a request is sent until the
  reply line arrives, for both action and discard requests.
- Any single reply must arrive within **5 s** *(prov.)*.
- Wall-clock kill per match: **180 s (Stage 1)** and **450 s (Stage 2)** *(prov.)*.
- Start-up: 5 s from launch to ready for `init`. **Not charged** to the bank.
- Crash, exhausted bank, a reply over 5 s, or the wall-clock kill all **forfeit** the rest of the
  match: a loss, and the opponent gets Δ = +C.
- stdout carries protocol JSON only, flushed after each message. stderr is for debugging only,
  capped at 64 KB per match and never parsed.
- No state is kept between matches (the bot starts fresh each match). Randomness is allowed.
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

## Still unknown (wait for the Problem Statement, 1 Nov)

- The exact showdown rule (any 5 of 7?), edge cases and worked examples.
- Final values of the provisional limits: RAM, time banks, per-reply limit, wall-clock kill and C.
- The organisers' starter kit and its local match runner (Protocol 12 mentions it; we don't have it).
