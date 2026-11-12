# Brief for every agent (read all of it before you start)

You are one of 20 agents working in parallel on poker bots for **Discard Hold'em, heads-up**. 10 agents improve one of
ten existing sparring bots; 10 agents each build a brand-new strong bot with a different technical approach. You have
**45 minutes of wall-clock time**. Be fast and practical; a working, tested, modestly better bot beats an ambitious
unfinished one. If you run out of time, deliver what works and say so.

## The game
- 2 players, stacks 200, blinds 1 (button, also "small blind") and 2 (big blind). Button acts first preflop and
  **last after the flop**. Max 4 raises per street. A hand: each player gets **3** hole cards; preflop betting;
  flop (3 cards) betting while holding 3 cards; then both players **discard one card at the same time and the
  discards are shown to each other**; then turn (4th board card) and river (5th) betting with 2 cards each;
  showdown: best 5-card hand from the 2 kept cards + 5 board cards. Ordinary poker hand ranks.
- A match = 2 legs of 200 hands (Stage 1), every deal played twice with seats and hole cards swapped (duplicate).
  Each leg is a fresh process (no memory across legs). Time bank 30 s per leg (`time_bank_ms` in `init`),
  5 s per reply hard limit. The bot must never crash, never print anything but protocol JSON to stdout, never write
  files, open sockets or start processes. **Target: mean reply time <= 20 ms, worst <= 80 ms.** Track your own time.

## Protocol (JSON lines, official engine `starter_kit/engine.py`)
Messages to the bot: `init` (total_hands, time_bank_ms, ...), `new_hand` (hand_id, seat "button"|"big_blind",
hole_cards [3 cards like "As","Td"]), `action_request` (street, board, pot, my_bet, opp_bet, to_call, my_stack,
opp_stack, legal_actions subset of fold/check/call/raise, min_raise & max_raise only when raise is legal,
raises_left, history = list of {street, actor "me"|"opp", action, amount}), `discard_request` (hole_cards, board),
`discard_result` (my_discard, opp_discard, hole_cards = the 2 you kept), `hand_result` (result "fold"|"showdown",
net, board, my_hole_cards, opp_hole_cards (only at showdown), opp_discard, history), `notice`, `match_end`.
Replies: `{"type":"action","action":"fold|check|call|raise","amount":N}` (amount = raise-to total, within
[min_raise, max_raise]) and `{"type":"discard","card":"As"}`. History amounts are raise-to / call-to totals on that
street. Read `starter_kit/engine.py` if you need exact details.

## Rules for the code
- Python 3.11 (`/Users/panavrg/cfr_pokerbot/.venv311/bin/python`), standard library + numpy only. Everything your bot
  needs lives in **your own folder** (a copy of any helper file is fine). No imports from the repo's `shared/` or
  `botsrc/` at run time.
- Write everything yourself. Do **not** copy code from `logs/v16.noindex`, `logs/v6.noindex`, `logs/tier3x.noindex`
  or any other bot you did not write in this session. Our own helper `eval/bots/spar/common.py` may be copied and
  changed (own evaluator, 1,755-class 3-card preflop table, range-weighted Monte Carlo equity, learning from
  showdowns).
- Do not edit anything outside your own folder. Do not `git commit`, `git push`, start training, use the network, or
  touch `dist/`. Do not change other agents' folders.
- Never use friend's bot `v6` or `tier3x` for tuning. Do not run `dist/bot.py` (too heavy for this machine).

## Testing (the machine is shared by 20 agents: obey this)
- Check legality and speed of your bot: `.venv311/bin/python eval/bots/spar/fuzz.py YOUR/bot.py` (must PASS).
- Play matches ONLY through the slot limiter, one worker at a time, at most 10 matches per command:
  `.venv311/bin/python eval/bots/slots.py -- .venv311/bin/python eval/bots/spar/play.py A B --matches 10 --workers 1 --seed-base N`
  A and B are bot names of the spar set (eqtag trapper potctl polar betfold light3b donk adapt tilt discardread), or
  paths to any bot file. Output: every match, wins/draws/losses, chips per hand with a 95% interval (A's view).
  Each match takes about 35-60 s of one slot; **your total budget is 24 matches**. Use them wisely.
- Opponents you may test against: `logs/v16.noindex/bot/bot.py` (a strong equity+table bot; your main yardstick),
  the spar bots (`eval/bots/spar/<name>/bot.py`; `eqtag` is the baseline), and your own earlier versions.
- **Overfitting rule:** develop on your dev seed range, then confirm the final version once on your confirm seed
  range (given in your task). Never hard-code anything specific to v16 or to a seed. Report both numbers; if the
  confirm result is much worse than dev, say so plainly.
- Matches have large variance (20 matches give about +-0.6 chips/hand): do not claim improvements the interval does
  not support.

## Report (your final message; under 250 words, plain language)
1. What you built or changed (3-5 bullets).
2. Files: the full path(s) of the finished bot.
3. Test numbers: for each test, opponent, matches, won-lost, chips/hand with interval, dev or confirm seeds.
4. Fuzz result (replies, worst ms).
5. Honest caveats: sample size, what did not work, overfit risk.
If your final version is not better than the starting point, deliver the best version you have and say so.
