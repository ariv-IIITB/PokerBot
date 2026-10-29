# Protocol adapter guide

How to connect the bot to an engine's wire format. The real format is now known: `docs/rules/protocol.pdf`
(JSON lines). Its adapter is `bot/protocols/pokerbots.py` (Part 4, phase C) and the default; the other
formats are mock formats for tests (the test suite defaults to `placeholder` in `tests/conftest.py`).

The real format is the one that needs state: opponent actions arrive only in `history`, so the adapter
keeps per-hand state and turns each wire message into **several** neutral messages (or none), in the order
the lab engine would have sent them. Things worth knowing:

- `parse_line` may return a list, `encode_message` may return `""` or a list of lines (see below).
- `discard_request` does not list the opponent's last flop action: it is inferred (they called our bet or
  raise, or checked behind our check when we are the big blind), emitted before the flop, and skipped when
  `history` lists it later. After an all-in preflop the opponent's call is inferred the same way.
- The opponent's discard arrives as a card, never as an index into their hidden hand: `OppAction(special)`
  carries the placeholder `"0"` and the `reveal` `Info` carries the real card (`hides_opponent_choice`).
- `discard_result` is turned into the engine's own per-seat message order; `bot/sim/replay.py` aligns card
  messages by order, so it must match.
- Test it with the kits in `tests/kit/`: the round trip (`check_round_trip("pokerbots", "discard_holdem")`)
  and transcripts (`tests/fixtures/protocol/example_hand.txt` is Protocol section 10).

## What an adapter is

Everything that knows a wire format lives in `bot/protocol.py` (the neutral message classes)
and `bot/protocols/` (one module per format). Brains, state, the game rules and the simulator
only ever see the neutral objects:

| Neutral object | Meaning |
|---|---|
| `MatchInfo(hands, timebank, sb, bb, stack)` | match header |
| `HandStart(hand_id, seat, stack, oppstack, timeleft, sb, bb, ante)` | seat 0 = small blind / button |
| `HoleCards(cards)` | our current hole cards (sent again whenever they change) |
| `BoardUpdate(street, cards, index)` | the full board so far (`index` with several boards) |
| `OppAction(action)` | the opponent's action (`Action`, raise amounts are **raise TO**) |
| `ActRequest(pot, tocall, mystack, oppstack, legal, timeleft, mybet, oppbet)` | our turn |
| `Showdown(oppcards)`, `Info(kind, who, cards, value)`, `HandEnd(delta)`, `MatchEnd()` | |

`LegalActions` carries fold/check/call, a raise range (raise-TO amounts, optionally a
discrete `raise_sizes` set or a `raise_step`), and an optional `SpecialOption` (finite choice
tokens, or a numeric range `lo..hi`).

An adapter implements four methods (`bot/protocols/base.py`):

```python
parse_line(line) -> None | Message | [Message, ...]   # bot side; None = ignore; ProtocolError if malformed
encode_action(action) -> str          # bot side: our reply
encode_message(msg) -> "" | str | [str, ...]   # engine side (the lab's SubprocessPlayer); "" = send nothing
parse_action(line) -> Action          # engine side
```

It may keep state between calls (for example the last `ActRequest`, to turn our raise-TO into
the engine's raise-BY).

## Step by step

1. **Collect real lines.** Save a few full hands of real engine traffic, both directions,
   including every special action the variant has (discards, bids, ...).
2. **Write the mapping table.** For each engine message, write which neutral message it becomes
   and how every field maps. Watch for:
   - *seat naming* (button/dealer vs small blind; which seat acts first preflop),
   - *raise convention*: raise TO a total, raise BY an increment, or "bet amount" — convert to
     raise TO using the current street bets (see `bot/protocols/terse.py`),
   - *pot*: does it include the current street's bets? (ours does),
   - *cards*: rank/suit letters, "10" vs "T", separators, jokers,
   - *time*: seconds or milliseconds, remaining bank or per-move clock,
   - *special actions*: how the engine names options; map them onto choice tokens
     (`"0"`, `"0+2"`, `"none"`, `"yes"`, numbers for bids).
3. **Copy the closest example** — `bot/protocols/jsonl.py` (structured) or
   `bot/protocols/terse.py` (positional tokens, raise-BY, different seat names) — to
   `bot/protocols/<engine>.py` and edit it. Unknown message types must return `None`;
   unparseable known ones must raise `ProtocolError` (never anything else).
4. **Register it** in `ADAPTERS` (`bot/protocols/__init__.py`) and add a few malformed example
   lines to `MALFORMED` in `tests/helpers.py`.
5. **Run the conformance suite**: `.venv/bin/python -m pytest tests/test_adapters.py`.
   It round-trips every message and action shape, fuzzes garbage lines, checks EOF handling
   and plays full matches over the wire on several variants.
6. **Run the whole suite on it**: `POKERBOT_PROTOCOL=<engine> .venv/bin/python -m pytest -n auto`.
7. **Replay the saved real lines** through `bot.main --protocol <engine>` and check every reply
   by eye against the legal options.
8. **Make it the default**: set `DEFAULT` in `bot/protocols/__init__.py` (the submission package
   uses it), or pass `--protocol` in the engine's launch command.

## The two mock adapters (proof that swapping works)

| Adapter | Lines | Differences from the placeholder |
|---|---|---|
| `bot/protocols/jsonl.py` | 153 | one JSON object per line, named fields |
| `bot/protocols/terse.py` | 207 | single-letter tags, positional fields, concatenated cards, **raise BY** in legal ranges and replies, `D`/`B` seat names |

Both pass `tests/test_adapters.py`, and the full test suite passes with
`POKERBOT_PROTOCOL=json` and `POKERBOT_PROTOCOL=terse`.

## Red flags

- The engine sends our hole cards only once but changes them (draws/swaps) — the adapter must
  re-emit `HoleCards` after every change, or the simulator's replay will not line up.
- The engine reveals the opponent's private choices only at showdown — fine; map hidden choices to
  `OppAction(Action.special("hidden"))`.
- Several boards with no board index — add the index from the message order.
- A per-move clock instead of a bank — map it to `timeleft` = what the bot may still use this
  move, and set `TimingConfig` accordingly.
