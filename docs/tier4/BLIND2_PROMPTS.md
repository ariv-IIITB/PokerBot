# Second blind opponent set: prompts for 9 bots (give these to Gemini or any other LLM)

Purpose: nine fresh opponent bots in styles unlike our pool, used **only** as a final generalisation test
(run once at the end with `--pool blind2 --final`; nobody tunes on them). Do not show the LLM anything about our bot.

## How to use

For each bot below, open a **new chat** (fresh context each time, so the nine don't copy each other), attach
`docs/rules/rulebook.pdf` and `docs/rules/protocol.pdf`, and paste: the BASE PROMPT, then that bot's STYLE BRIEF.
Save the returned file as `Opps/discard_blind2/<name>/bot.py` (one folder per bot). Don't edit the code by hand
except to fix a crash; if it crashes, ask the LLM to fix it, not us. Then tell the manager and a session will register them
(`blind2` pool, `--final` only) and run a legality smoke test.

## BASE PROMPT (same as the one used for the existing pool bots)

> Build a bot for this poker competition. The two attached PDFs are the official rules and protocol. It must never
> crash or time out, and it should win as many matches as possible. Deliver a complete bot.py (or a folder with bot.py
> at the top level) that runs with `python3.11 bot.py`, uses only the standard library, numpy and scipy, and speaks the
> protocol exactly as specified. Give me the full code, no placeholders.
>
> Play style for this bot: <PASTE THE STYLE BRIEF HERE>
> Keep each decision under 0.5 seconds on average.

## STYLE BRIEFS (one per chat)

1. **blind2_probe** (small-ball prober): leads into the previous aggressor with small probe bets (20–35 % pot),
   folds to raises unless it has a strong made hand, rarely bluffs the river.
2. **blind2_checkraise**: checks strong hands and draws on the flop and turn to check-raise, bets the river for thin value
   only when checked to, rarely opens preflop with weak hands.
3. **blind2_riverbluff**: plays solid value poker through the turn, then bluffs the river with missed draws and air
   at a high frequency, folds to river raises.
4. **blind2_rock**: tight-passive: plays only strong starting hands, bets only when it has a made hand, calls with
   medium strength, folds weak hands to pressure, never bluffs.
5. **blind2_tit_for_tat**: tracks how often the opponent folds to its bets and calls its raises; raises its bluff
   frequency while the opponent folds too much and tightens up (value only) when the opponent calls too much;
   recomputes every 30 hands.
6. **blind2_sizetell**: value bets large (70–100 % pot), bluffs small (25–40 % pot), deterministic sizing by
   hand strength bucket; calls small bets wide and folds weak hands to large ones.
7. **blind2_discardsmart**: puts most of its effort into the discard decision (simulate which kept 2-card hand has the
   best equity against the opponent's likely range, using the opponent's visible discard), then plays straightforward
   equity-based poker: bet when ahead, call by pot odds, fold otherwise.
8. **blind2_mixed**: randomised mixed strategy: estimates equity by Monte Carlo against a weighted opponent range, then
   chooses actions with fixed probabilities by equity band (for example equity 0.55–0.65: bet 50 %, check 50 %),
   so it is hard to read; mixes bluffs at about one third of its value-bet frequency.
9. **blind2_position**: strongly position-aware: very aggressive on the button (raises most hands preflop, bets most
   flops), tight and passive out of position (check-calls, check-folds weak hands), 3-bets light only in position.

## What the returned code must satisfy (check before handing it back)

- Starts fresh per match, reads JSON lines from stdin, writes JSON lines to stdout with flush, answers every
  `action_request` and `discard_request`, exits on `match_end`.
- No file reads or writes, no network, no subprocess, only stdlib + numpy + scipy.
- Legal actions only (raise amounts are "to" amounts, min-raise rules from the rulebook), a discard card from its own hand.
- Never crashes on unknown message types (ignore them).
- Average well under 0.5 s per decision (the bank is 60 s per 400 hands).
