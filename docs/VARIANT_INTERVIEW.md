# Variant interview

Turn the official rules document into `variant/active.json`. Go through the questions in
order; each answer maps to spec fields (`variant/spec.py`). Start from the closest preset in
`variant/catalog/` (`.venv/bin/python -m lab.new_variant --from <preset>`). Mark every
answer you are unsure of and ask the organisers.

## A. Deck
1. Which ranks are in the deck, low to high? → `deck.ranks` (short deck: `"6789TJQKA"`)
2. Which suits? → `deck.suits`
3. Jokers? How many? → `deck.jokers` (and `evaluation.wild.jokers = true`)
4. More than one deck shuffled together? → `deck.copies`
5. Any cards removed? → `deck.removed`

## B. Dealing and board
6. How many hole cards each, dealt when? Any dealt face up? → `deal_hole {n, face_up}`
7. How many betting rounds, and how many board cards before each? A round with no new cards?
   → `deal_board {n}` + `betting` steps (n may be 0)
8. Burn cards? Shown? → `deal_board {burn, burn_revealed}`
9. Several boards dealt in parallel? → `deal_board {boards}`
10. "Run it twice" after an all-in? → `showdown {runs}`

## C. Card manipulation
11. Discards: how many, when, in what order (BB first / SB first / simultaneous), seen by whom
    (public / private / later), where do they go (board / muck / opponent), optional?
    → `discard {...}`
12. Draws (replace cards): min/max, cost, is the count public? → `draw {...}`
13. Swaps: with the opponent / a board card / the deck; optional / forced / random? → `swap {...}`
14. Choose-from: offered how many, keep how many? → `choose {offer, keep}`
15. Peeks: at what, for how much? → `peek {target, cost}`
16. Exposing hole cards: chosen or random? → `expose {n, chosen}`

## D. Showdown
17. Best how many cards? From which cards (any / exactly x hole cards / at least / at most)?
    → `evaluation.hand_size`, `hole_exact`, `hole_min`, `hole_max`
18. High, low (2-7 or A-5), or hi-lo (with a qualifier like 8-or-better)? → `evaluation.kind`,
    `low_qualifier`
19. Any change to the hand ranking (e.g. flush beats full house)? → `evaluation.category_order`
20. Wild cards? → `evaluation.wild` (`{"rank": "2"}`, `{"jokers": true}`, `{"cards": [...]}`)
21. A completely different scoring rule? → register a function in `bot/game/scoring.py` and use
    `evaluation.kind = "score"`
22. Several boards: how is the pot split? (default: evenly per board)

## E. Betting
23. No-limit, pot-limit or fixed-limit (bet sizes per round)? → `betting.structure`, `fixed_bets`
24. Blinds, antes, straddle? Who posts what? → `small_blind`, `big_blind`, `ante`, `straddle`
25. Minimum raise rule? Raise cap per round? → (min raise = last full raise) `max_raises`
26. Only certain bet sizes allowed (pot fractions, multiples)? → `bet_sizes`, `bet_multiple`
27. Who acts first preflop / postflop? Any round with a different order? → `preflop_first`,
    `postflop_first`, `betting {first}`
28. Check-raising allowed? → `check_raise`

## F. Payoffs and side mechanics
29. Bounty rank? Fixed / random / chosen; bonus or multiplier? → `bounty {...}`
30. Auctions / bidding: for what prize, sealed first- or second-price or all-pay, where do the
    bids go, how are ties broken? → `auction {...}`
31. A side market / prediction / quote? On what quantity? → `market {...}`
32. Pot multipliers, rake? → `payoffs: [{"type": "multiplier"...}, {"type": "rake"...}]`

## G. Match
33. Hands per match, time bank (seconds, per match or per move)? → `match.hands`, `time_bank_s`
34. Starting stack; do stacks reset every hand? What happens on a bust? → `starting_stack`,
    `reset_stacks`, `bust_ends_match`
35. Do the blinds go up during the match? → `match.blind_schedule`

## H. Information
36. Is any action or card shown to only one player? Revealed later? Revealed on request?
    → visibility parameters of the steps above

## Red flags: a new plugin is needed (see WRITING_A_PLUGIN.md)
- A decision that isn't betting and isn't any step above (e.g. choosing which board to play,
  voting, trading cards for chips with the house, re-ordering cards).
- Cards that move somewhere new (a "side pile", cards passed between hands later).
- A payment rule that depends on something other than the final hands (e.g. a bonus for
  winning without showdown, for the number of raises, for the order of reveals).
- Information rules that differ by street or by the player's stack.
- More than two players, or any action taken by the house/dealer during the hand.
- Timing rules that are per action rather than a bank (→ `bot/timing.py`).
- The protocol's own quirks: see `PROTOCOL_ADAPTER_GUIDE.md`.

## When you're done
`.venv/bin/python -m lab.new_variant --spec variant/active.json` validates it, prints the
hand program in plain English (read it next to the official rules!), and runs a smoke fuzz.
