# Part 4 plan: Discard Hold'em, from rules to a shipped "Ivey-style" bot

Written 2026-10-28 for the implementing model (Sonnet). **Finalized 2026-10-29** after phases A–C:
done phases are marked, what the build changed is recorded, and Phase E now carries the lessons
from the Hold'em LLM bots into Tier 2. The person who runs it reviews after every phase.
Current state: `docs/STATUS.md`.

## How to use this plan

- **Read first, every session:** `CLAUDE.md`, `docs/rules/SUMMARY.md`, and this file. The PDFs in
  `docs/rules/` are the source of truth. If this plan conflicts with them, the PDFs win; stop and say so.
- **One phase per session.** Do the "Check first" list before writing code. End each phase with:
  - all tests green on Python 3.11 (`.venv/bin/python -m pytest -n auto`, and `-m slow` where the
    phase says so);
  - a short report (what was built, tests, numbers, files changed);
  - a commit `phase 4X: ...`;
  - **merge into `main` and push `main`** (the next session only sees GitHub);
  - update `docs/STATUS.md`;
  - then **stop and wait for OK**.
- **Each phase starts by reviewing the previous one** against the code and tests (the reports
  have missed things before). The first numbered step of every phase below is that review.
- **Never copy code from `Opps/`** into `bot/` (ideas only; similarity checks run on submissions).
- **Never tune on held-out opponents** (Phase F sets the list).
- If three fixes in a row fail, stop and report. Don't guess file contents, signatures or rules:
  read or grep.
- Keep diffs small and in the existing style. Comments say *why*, in one line.
- Numbers are integers (chips). Tests are seeded and deterministic.

### Phase overview

| Phase | What | Depends on | Status / target |
|---|---|---|---|
| **A** | Framework: the shared tools every later phase uses | — | ✅ done `d3146b1` |
| **B** | Discard Hold'em rules in the engine | A | ✅ done `a44e234` |
| **C** | Real protocol adapter (both directions) | A, B | ✅ done `d131932`, `dd51c98` (review in D1) |
| **D** | Ship-safe: no file reads, `bot.py`, package, timing, lock → **upload #1** | C | ✅ done `accb344` (user uploads) |
| **E** | Tier 2 plays the real game well: discard, tables, **lessons from the LLM bots** → **upload #2** | D | Nov 1–3 |
| **F** | Opponent pool: the user's LLM bots, train/held-out split, baseline report | C (+ user's bots) | when the bots arrive (target Nov 3) |
| **G** | Tier 3: the "Ivey" style, built one behaviour at a time → **upload #3** if it ships | E, F | 🟡 built (2026-10-30, `docs/reports/TIER3.md`); pool runs and G8 wait for the held-out split |
| **H** | Problem Statement update (1 Nov, inserted when it lands) and final freeze | any | Nov 1, Nov 13–15 |

**Uploads.** A valid upload must exist at all times. Upload after D (safe Tier 2), after E (better
Tier 2), after G if Tier 3 ships, and the final one at H. Each is recorded in `docs/SUBMISSIONS.md`.
Only the user can upload (Unstop).

The framework (A) is built once. B–G then become "add data and cases to the framework", not
one-off scripts. Each later phase names the framework pieces it uses.

---

## Phase A — Framework

> **Done (`d3146b1`).** As built:
> - `lab.eval` matches the old loop exactly only for brains that don't depend on wall-clock time.
>   Tier 2's sample counts depend on speed, so equal seeds don't give equal chips. Always compare
>   with SEs.
> - `lab/opps/accounting.py` is a thin front over `lab.eval --report accounting` (bookkeeping in
>   `lab/opps/track.py`).
> - The sandbox allow-list has a third file, `bot/game/rules_spec.py` (it reads
>   `variant/active.json`). Phase D removes all three.

Goal: six small tools that turn every later change into "add a case, run the check". No bot
behaviour changes in this phase.

### Check first
- `tests/helpers.py`: `scripted_hand_messages`, `scripted_messages`, `scripted_match` already
  exist. Read them and reuse them; don't duplicate.
- `tests/test_betting.py` and `tests/test_payoffs.py` show how hands are scripted on a rigged deck.
- `tests/test_imports.py` already does static checks on `bot/` (imports, no writes).
- `lab/opps/accounting.py` and `lab/opps/profile.py` hardcode `lab/opps/holdem_100bb.json`.

### A1. Scenario kit — `tests/kit/scenario.py`
A data-driven way to play one hand through `bot/game` on a rigged deck and assert the state at
each step.

```python
Scenario(
    spec="variant/catalog/discard_holdem.json",
    holes={"SB": ["As","Kd","7c"], "BB": ["Qs","9h","9c"]},   # SB = button
    board=["Ah","7d","2s","3c","4h"],
    steps=[                     # (actor, action, expected-before-acting)
        ("SB", "raise 6", {"legal": {"fold","call","raise"}, "min": 4, "max": 200}),
        ("BB", "call", {}),
        ("BB", "check", {"street": "flop"}),
        ...
        ("SB", "discard Kd", {}), ("BB", "discard Qs", {}),
    ],
    expect={"deltas": {"SB": 12, "BB": -12}, "showdown": False},
)
```

- `run_scenario(s)` builds the deck order the engine deals from (see `lab/engine.py:deck_for` and
  how `Hand` consumes the deck), plays the steps through `bot/game` (`advance`, `legal_actions`,
  `act` from `bot/game/runner.py`) and checks every expectation.
- On a mismatch, the failure message names the step.
- It also checks chip conservation and that no card is visible to the wrong player (reuse
  `bot/game/observation.py`).
- Cards are given as strings and parsed with `bot/cards.py:parse_card`.

### A2. Transcript kit — `tests/kit/transcript.py` + `tests/fixtures/protocol/*.txt`
Replays a wire-level conversation against the bot.

- Fixture format: one line per message, `E> {json}` (engine to bot) or `B> {json}` (the expected
  bot reply). An expected reply may be partial: `B> {"type":"action"}` checks only the given keys.
  `B> ANY` matches any valid reply to the request.
- `replay_transcript(path, brain="tier0", adapter="pokerbots")` feeds the `E>` lines to
  `bot.main.Bot` (in-process, `out=io.StringIO()`), checks one reply per request and **no reply
  to anything else**, and returns the final `GameState`.
- The same file also drives the **engine side**: the adapter's `parse_action` must decode every
  `B>` line.

### A3. Round-trip conformance — `tests/kit/roundtrip.py`
The generic correctness check for any adapter.

1. Play N seeded hands in the lab engine (`lab/engine.py:play_match`) with two **recording**
   in-process players. Each records the neutral messages it receives and the `GameState` snapshot
   at every `ActRequest`.
2. For each seat, push the recorded stream through `adapter.encode_message` (engine side), then
   through a fresh adapter's `parse_line` (bot side), into a fresh `GameState`.
3. At every `ActRequest`, assert that the decoded state equals the recorded one on:
   - `hand_id`, `seat`, `hole`, `board`, `street`, `pot`, `tocall`, `my_bet`, `opp_bet`, the stacks;
   - `history` (kind and amount, per street);
   - the legal set;
   - the revealed opponent discard.
4. Report the first mismatch with the full message context.

Parametrize it over adapters. It must pass for `placeholder`, `json` and `terse` today; Phase C adds
`pokerbots`.

### A4. Sandbox guard — extend `tests/test_imports.py` + new `tests/test_sandbox.py`
- **Static (AST over `bot/`):**
  - keep the existing checks;
  - fail on any call to `open`, `np.load`, `np.fromfile`, `Path.read_text`, `Path.read_bytes`,
    `os.listdir`, `os.scandir`, `glob`, `os.system`, `os.fork`, `os.exec*`, `os.popen`, and on
    importing `threading.Thread` usage beyond `current_thread`;
  - temporary allow-list: `bot/brains/params.py` and `bot/sim/tables.py` (Phase D removes them).
    Mark each allowed line with a `# sandbox-allow: <reason>` comment and fail if the comment is
    missing.
- **Runtime:** run `bot.py` (or `python -m bot.main` until D) in a **subprocess** with a
  `sys.addaudithook` installed by a tiny wrapper script (`tests/kit/sandbox_run.py`).
  - Feed it the Protocol §10 transcript (or the placeholder transcript until C).
  - Fail on audit events `open` whose path does not end in `.py`, `.pyc`, `.so` or `.pth` (import
    machinery is fine), and on `socket.*`, `subprocess.Popen`, `os.system`, `os.fork`, `os.exec`,
    `os.posix_spawn`.
  - Print the offending event.
  - Mark it `xfail(strict=True)` until Phase D, so it flips to a pass when D lands.

### A5. Embed generator — `tools/embed_data.py` → `bot/embedded.py`
- Generates one Python module holding everything the bot used to read from disk:
  - `SPEC` (the active variant as a dict);
  - `PARAMS = {"tier1": {...}, "tier2": {...}}` (from `bot/config/*.json`);
  - `TABLES` (base64 of `np.save` bytes for each table in `data/<variant>/`, plus its `meta`, or `None`).
- Header: "generated, do not edit", the source file hashes, and the generation command.
- Add a test that regenerates in memory and asserts the committed `bot/embedded.py` is
  current. On failure it prints the command to run.
- Size guard: fail if `bot/embedded.py` is over 3 MB (the submission limit is 5 MB).
- Phase A only builds the generator. Phase D switches the loaders over.

### A6. Experiment runner — `lab/eval.py` (replaces the hand-run loops in `lab/opps/*.py`)
- One CLI:
  `python -m lab.eval BRAIN[:variant=json] --pool train|heldout|NAME... --pairs 50 --locks on|off
  --variant <spec> [--hands 400] [--bank 60] [--report accounting,profile] [--out logs/<name>.txt]`
- It reuses `lab.harness.run_duplicate`. Add `--variant` to `lab/opps/accounting.py` and
  `lab/opps/profile.py`, and call them through it.
- Output: the same text formats as the existing `logs/*.txt`, one summary line per opponent with
  `bb/hand ± SE` and the match score, plus the accounting and profile blocks when asked.
- `--pool heldout` needs `--final` (a guard against tuning on held-out bots).
- `--compare A B` prints the per-opponent difference with SE, plus a **keep / drop** verdict. Keep
  only if the target opponent improves by more than 2 SE *and* no other opponent drops by more than 2 SE.
- A `TARGETS` dict (the action-profile ranges from Phase G) and `--check-profile` print pass/fail
  per spot.

### Done when
- The kits exist, with one example test each: a Hold'em scenario, the placeholder transcript, and
  the round-trip for the existing adapters.
- The static sandbox guard passes with the allow-list; the runtime guard xfails.
- `lab.eval` reproduces `logs/tier2_vs_opps_nolock_50seeds.txt` for opp1 at 5 pairs (same numbers
  for the same seeds).

---

## Phase B — Discard Hold'em rules

> **Done (`a44e234`, reviewed).** As built:
> - `discard_holdem` is the active variant.
> - `betting.blind_counts_as_raise` (default off) makes the BB count toward the cap.
> - `bot/game/steps/cards.py:fallback_discard` and `safe_action_for_hole` are the rules' discard
>   fallback, used by the lab engine, Tier 0 and the bot's emergency/error paths.
> - 30 tests in `tests/test_discard_holdem.py`.
> - Baseline on this game: `logs/discard_holdem_tier{1,2}_vs_bots.txt`.

### Check first
- `variant/catalog/pineapple.json` is close but **not** the same program: it discards privately and
  *before* flop betting. Discard Hold'em discards *after* flop betting, publicly, and has the raise
  cap. `tests/fixtures/specs/public_discard.json` (Phase A) already covers public discards in the
  round-trip.
- `bot/game/steps/betting.py`:
  - `Betting.begin` resets `st.raises = 0` on later rounds, and round 0 starts at 0 (`bot/game/state.py`).
    So the BB does **not** count as a raise today.
  - `legal()` computes `rmin = high + max(st.last_raise, bb)` and `rmax = all_in`.
- `bot/game/steps/cards.py:Discard.perform`: with destination `muck`, it calls
  `reveal(..., "discard")`, which emits a public `reveal` event when visibility is `public`.
- `lab/engine.py:Hand.ask`: on an illegal reply it uses `safe_action(legal)` (check, else fold).
  For a special step, check what `safe_action` does.
- `bot/cards.py`: `SUITS = "cdhs"`. The rules' discard tie-break order is **s, h, d, c**, so card id
  order is NOT the rule order.

### Build
1. `variant/catalog/discard_holdem.json`:

   ```json
   {
     "name": "discard_holdem",
     "description": "Official Pokerbots 2026 game: 3 hole cards; 3-card flop; after flop betting both players discard 1 hole card simultaneously, face up, removed from play; turn; river.",
     "betting": {"small_blind": 1, "big_blind": 2, "max_raises": 4, "blind_counts_as_raise": true},
     "match": {"hands": 400, "time_bank_s": 60.0, "starting_stack": 200, "reset_stacks": true},
     "program": [
       {"type": "post_blinds"}, {"type": "deal_hole", "n": 3},
       {"type": "betting", "round": "preflop"}, {"type": "deal_board", "n": 3},
       {"type": "betting", "round": "flop"},
       {"type": "discard", "n": 1, "order": "simultaneous", "visibility": "public", "destination": "muck"},
       {"type": "deal_board", "n": 1}, {"type": "betting", "round": "turn"},
       {"type": "deal_board", "n": 1}, {"type": "betting", "round": "river"},
       {"type": "showdown"}
     ]
   }
   ```

   Copy it to `variant/active.json`. Validate with `python -m lab.new_variant` and read the
   printed program next to Rulebook §4.
2. **`blind_counts_as_raise`** (new `BettingSpec` field, default `false` so every other preset is
   unchanged):
   - add it to `variant/spec.py` (field + validation);
   - pass it into `Betting`; in `Betting.begin` for round 0, set `st.raises = 1` when it is on;
   - add a `describe()` mention.
   - `rules_spec.py`'s legacy path stays `False`.
3. **Stage 2** is not a second spec file (`spec_hash` keys the precomputed tables, so a second
   spec would orphan them). Use `--hands 1000 --bank 150` on `lab.harness` / `lab.eval`.
4. **Illegal or missing discard** in the lab engine: discard the lowest-ranked hole card, and on
   equal ranks the first suit in the order **s, h, d, c**.
   - Put the rule in one helper, `bot/game/steps/cards.py:fallback_discard(cards)`, used by
     `Hand.ask` when the reply to a discard is illegal.
   - The bot uses the same helper as its own Tier 0 discard. Today `bot/actions.py:safe_action`
     returns `legal.special.default()`, the first option, i.e. the first card, so it needs the
     card values to apply the rule. Do it where the hole cards are known (`bot/main.py:Bot.choose`
     fallback and the emergency path); `safe_action` itself stays card-blind. It matches the
     official starter bot and costs nothing.
5. The illegal-action rule (check if legal, else fold) already matches. Keep it and add a test.

### Tests (all scenarios via A1, in `tests/test_discard_holdem.py`)
- **Worked example (Protocol §10):**
  - preflop: button raises to 6, BB calls;
  - flop `Ah 7d 2s`: BB checks, button bets 6, BB calls;
  - discards: button `Kd`, BB `Qs`;
  - turn `3c`: check, check;
  - river `4h`: BB checks, button bets 10, BB folds → **button +12, BB −12**.
- **Raise cap:** preflop allows exactly **3 voluntary raises**, then `raise` is not legal. Postflop
  allows exactly **4 bets/raises**.
- **Min-raise:**
  - first preflop min-raise-to = 4;
  - after a raise to 6, the re-raise minimum is 10;
  - postflop opening bet minimum = 2;
  - after a bet of 10, the minimum raise-to = 20;
  - an all-in below the minimum is the only legal raise (`min == max`).
- **Discard skipped** when someone folds preflop or on the flop.
- **Discard still happens** when both are all-in preflop: the board is dealt, and both discard
  after the flop.
- **Discards are public and dead:**
  - after the discard each player sees both discarded cards (`reveal` event, visible to ALL);
  - the cards are in `st.muck`, not on the board, not in any hand;
  - showdown uses exactly the 2 remaining hole cards + 5 board cards.
- **Fallback discard:** `[7s, 7c, Kd]` discards `7s`; `[2h, 2d, Ac]` discards `2h`;
  `[Ts, Jh, 9c]` discards `9c`.
- **Illegal action:** a raise outside the range becomes check if checking is legal, else fold.
- **Chip conservation and visibility:** a 2,000-hand fuzz of `discard_holdem` (`lab.fuzz` or
  `lab.new_variant`'s smoke fuzz) with `audit=True`.

### Done when
All of the above pass, the existing preset tests are unchanged, and the report lists the spec and
the one engine change (`blind_counts_as_raise`).

---

## Phase C — Real protocol adapter

> **Done (`d131932`, `dd51c98`); reviewed as step D1.** As built, differing from the text below:
> - **Missing-action inference was generalized.**
>   - All-in preflop: the opponent's call only shows in `hand_result`. It is emitted first and
>     skipped when `history` lists it later.
>   - The button's check closes the flop round. "They checked behind" applies only when we are the BB.
> - **A malformed request gets a blind safe reply** instead of silence (silence would forfeit by
>   timeout; the engine corrects illegal replies).
> - **The test suite defaults to the mock `placeholder` format** (`tests/conftest.py`). The bot's
>   default is `pokerbots`. The real format is tested explicitly.
> - `pokerbots` round trips skip `pineapple` and `exposed_hole` (not this game).
> - The starter bot is `lab/sparring/starter_bot.py`, seated with `lab.eval --pool starter`.
> - **Smoke matches** over the real protocol (400 hands): tier2 vs tier2 and tier2 vs starter, with
>   0 errors and 0 forfeits. But one tier2 used **~34 s of its 60 s bank** on this laptop (see D5).

### Check first
- `bot/protocols/base.py` (the interface), `bot/protocols/jsonl.py` (the mock JSON adapter; field
  names differ from the real ones), `bot/protocol.py` (the neutral messages), and
  `bot/main.py:Bot.handle_line` / `on_message`.
- `lab/players.py:SubprocessPlayer`: `notify` sends one line per message; `act` sends the request
  line, then reads one reply.
- `lab/engine.py:flush_events`: which neutral messages the engine sends, and in what order. Use
  A3 to record the exact stream for `discard_holdem`.
- `bot/sim/replay.py:_sample_hidden_choice`: how an opponent's special choice that can't be
  matched is sampled.

### The one interface change (do it first, in its own commit)
The real protocol packs several neutral messages into one line (e.g. `new_hand` = `HandStart` +
`HoleCards`; `action_request` = new opponent actions + board + `ActRequest`). The engine side
must also **merge** several neutral messages into one line, or into none.

- `Adapter.parse_line(line)` may return `None`, one `Message`, or a **list** of `Message`s.
  `Bot.handle_line` normalizes to a list and calls `on_message` for each. At most one of them is a
  request; reply once, after the last.
- `Adapter.encode_message(msg)` may return `""` (send nothing) or a **list** of lines.
  `SubprocessPlayer.notify` / `act` normalize and send each non-empty line.
- Old adapters return single values and keep working. A3 must stay green for them.

### Build `bot/protocols/pokerbots.py` (`PokerbotsAdapter`, name `"pokerbots"`)
Register it in `ADAPTERS` and make it the `DEFAULT`. Also run the full suite with
`POKERBOT_PROTOCOL=placeholder` (a CI line in the report) so old tests still cover the others.

**Bot side (`parse_line`):** keep per-hand state: our hole cards, the board, the number of history
entries already turned into messages, and the last known action per street.

| Wire message | Neutral messages, in order |
|---|---|
| `init` | `MatchInfo(hands=total_hands, timebank=time_bank_ms/1000, sb, bb, stack=starting_stack)`. Store `per_response_ms` for the timer (D). |
| `new_hand` | `HandStart(hand_id, seat=0 if "button" else 1, stack, oppstack=opp_stack)`, then `HoleCards(3 cards)`. Reset hand state. |
| `action_request` | For each **new** history entry (`street`, `actor`, `action`, `amount`): emit `BoardUpdate` when the street changes (board from the request; street numbering exactly as the lab engine emits it, so check with A3), then `OppAction` for `actor == "opp"`. Skip our own entries, but check they match what we sent (warn on mismatch). Then `BoardUpdate` if the request's board is longer than ours. Then `ActRequest(pot, tocall=to_call, mystack=my_stack, oppstack=opp_stack, legal, timeleft=time_left_ms/1000, mybet=my_bet, oppbet=opp_bet)`. `legal` comes from `legal_actions`, `min_raise`, `max_raise`. |
| `discard_request` | First **infer the opponent's last flop action**, which `discard_request` doesn't list. Flop betting ended with no fold, so if the last known flop action is ours: our check → opponent checked; our bet/raise → opponent called. Emit that `OppAction`. Then `BoardUpdate` (flop) if not yet seen. Then `ActRequest` with `legal.special = SpecialOption("discard", <the exact option tokens the lab engine offers, e.g. "0","1","2">)`, `pot`, the stacks, `timeleft`. |
| `discard_result` | Exactly the messages the lab engine sends at this point (record with A3): an `OppAction(Action.special(<token>))` for the opponent's choice, the public `Info("reveal", ...)` events for both discards, and `HoleCards(remaining 2)`. We know the opponent's discarded **card**, not its index among their hidden cards. Their hole cards are unknown placeholders, so any index is equivalent: use the first option token, and put the real card in the `reveal` `Info`. **Test** that `bot/sim/replay.py:reconstruct` then treats that card as dead (never in the opponent's sampled holes, never dealt). |
| `hand_result` | Missing opponent actions from `history` (same diff), a `BoardUpdate` for unseen board cards, `Showdown(opp_hole_cards)` when `result == "showdown"`, then `HandEnd(net)`. |
| `notice` | Log to stderr, return `None`. |
| `match_end` | `MatchEnd()` (the main loop then exits). |
| unknown `type` / unknown fields | Ignore (`None` / skip). Blank line → `None`. Non-JSON or a broken known message → `ProtocolError` (the main loop already logs and continues). |

**Bot side (`encode_action`):**
- `fold` / `check` / `call` → `{"type":"action","action":"..."}`.
- `RAISE` → `{"type":"action","action":"raise","amount":N}` (a "to" amount; ours is already "to").
- `SPECIAL` → `{"type":"discard","card":"<our hole card at that index>"}`.
- Compact JSON, one line.

**Engine side (lab, stateful):**
- `encode_message` turns the neutral stream into real lines: buffer `HandStart` + `HoleCards` into
  `new_hand`; keep `BoardUpdate`, `OppAction` and our own actions as history; emit `action_request` /
  `discard_request` on `ActRequest`; `discard_result` after the discard; `hand_result` on `HandEnd`;
  `match_end`.
- `parse_action` reads both reply types and maps a discard card back to its index.
- With this, any bot that speaks the real protocol (the starter bot, the Phase F LLM bots, our own
  `bot.py`) runs in the lab as a `SubprocessPlayer(..., protocol="pokerbots")`.

### Tests
- **A2 transcript:** `tests/fixtures/protocol/example_hand.txt` from Protocol §10, with the history
  entries the PDF elides filled in.
  - It uses a **scripted test brain** (`tests/kit/scripted_brain.py`, which replies from a list) so the
    expected `B>` lines are exactly the PDF's: raise 6, raise 6, discard Kd, check, raise 10.
  - Final state: our hole cards `As 7c`, opponent discard `Qs` known, hand delta +12.
- **Robustness:** a malformed line, an unknown `type`, unknown fields in every message, a blank
  line, and a reply-less `notice` give no crash and no reply.
- **Never reply without a request:** the transcript checks this.
- **A3 round-trip** for `pokerbots` on `discard_holdem`: 200 hands, both seats, including folds,
  all-ins and showdowns.
- **Subprocess match:** our bot vs our bot over the real protocol, a full 400-hand
  `discard_holdem` match: 0 errors, 0 notices, 0 forfeits.
- **Starter bot:** save the official starter bot from Protocol §11 as `lab/sparring/starter_bot.py`
  (organiser material, lab only) and play 1 match against it through the real protocol.

### Done when
All of the above pass, and the old adapters still pass A3.

---

## Phase D — Ship-safe (no file reads, `bot.py`, package, timing, lock) → first upload

> **Done (`accb344`, zip `dist/upload1_phaseD.zip`, sha256 `2dab3f52…`).** As built, differing from the text below:
> - **D1 found:** a request that fails *after* parsing (not in the parser) got no reply and would
>   have forfeited: `Bot.handle_line` now always answers a request (blind safe reply). A broken
>   `discard_request` is answered from its own `hole_cards` when they can be read. New
>   `tests/test_pokerbots_spec.py` checks the engine-side wire lines against the PDF independently of
>   our parser (6 seeds). The round trip also held on 40 extra seeds (55k requests, both seats, all-ins).
> - The two load-sensitive tests: start-up is judged on the child's CPU time (wall bound loose), and
>   the match test counts deadline hits instead of banning `WARN`.
> - **Loaders removed:** `load_params` reads `bot.embedded.PARAMS`, `load_tables` reads
>   `bot.embedded.TABLES` (`np.lib.format.read_array` on base64, no `np.load`), `active_rules` reads
>   `bot.embedded.SPEC` or `$POKERBOT_VARIANT_JSON` (spec JSON *text*). The sandbox allow-list is empty
>   (only three marked lab helpers in `variant/spec.py`, never called by the bot); the runtime audit test
>   passes, also over the real protocol. `bot.py` sets `sys.dont_write_bytecode` so a read-only disk
>   sees no `.pyc` write attempts.
> - **Timing (the red flag):** measured 5.1–5.6 decisions per hand, not 3. Pacing is now 5.5 decisions,
>   safety 4.5, budgets capped at 1.2× the opening pace (before, savings were spent late: budgets grew
>   10× by hand 350 and a match used ~50 % of the bank), hard limit ≤ 0.3 × `per_response` (1.5 s, was up
>   to 15 s), rollout/PIMC batches sized to the budget. Real use ≈ 22–24 % of the bank, projected at 2×
>   44–49 % (limit 50 %), worst reply < 0.1 s (one 263 ms outlier in 1000 hands). Slow-machine tests:
>   `lab.engine.play_match(clock_scale=2)` charges every reply double (`tests/test_timing_slow.py`).
> - `lab.timing_bench` / `lab.memory_check` take `--cmd`, run over the real protocol, lock off by default
>   (`POKERBOT_BRAIN_CONFIG`, lab only), and fail above 50 % projected or a 0.5 s reply.
> - `tools/package_submission.py` builds `bot.py` + `bot/` + `variant/` + a fresh `bot/embedded.py`,
>   zips reproducibly (sorted, fixed timestamps), and runs every check on the **unpacked zip**.
> - Peak memory is 40 MB (no tables yet).

### Check first
- File reads in `bot/`:
  - `bot/brains/params.py:load_params` (reads `bot/config/*.json`);
  - `bot/sim/tables.py:load_tables` (`.npy` + `meta.json`, plus the `POKERBOT_DATA` env);
  - `bot/game/rules_spec.py:active_rules` (reads `$POKERBOT_VARIANT` or `variant/active.json`).
- `bot/timing.py:TimingConfig`:
  - `max_budget_s=0.25`;
  - `hard_bank_frac=0.25`, so the hard limit can reach **15 s** early in a match. **That breaks the
    5 s reply rule.**
- `tools/package_submission.py`: it copies `bot/config` and `data/`, and checks imports, startup,
  a smoke match, timing and memory.

### Build
1. **D1. Review Phase C first** (it was merged without review):
   - read `bot/protocols/pokerbots.py` and the multi-message interface change against
     `docs/rules/protocol.pdf` sections 4–7 and 9;
   - check the two generalized inference rules (see the Phase C box) with the round-trip kit on
     extra seeds, including all-in hands and both seats;
   - check what the "blind safe reply" sends for a malformed `discard_request`: it must be a
     `discard` message or nothing the engine would treat as worse than its own fallback;
   - rerun the fast and slow suites and report the counts. Fix what you find before step 2.
   - **Two load-sensitive tests** (found 2026-10-29, both pass alone; they fail under
     `pytest -n auto` on 14 workers):
     - `test_bot_subprocess.py::test_startup_time` (2.08 s under load);
     - `test_pokerbots.py::test_full_match_tier1_vs_tier2_over_the_real_protocol`, which asserts no
       stderr `WARN`, but under load the brain overruns its ~20 ms hard deadline ("brain exceeded
       hard deadline") and falls back to Tier 0.
     Make them robust: run them serially or mark them `slow`, and assert no errors or forfeits, not
     "no WARN". Count deadline hits and report them instead. **Treat the deadline hits as timing
     data for step 5:** a slower server looks like this load.
2. **Embed and switch the loaders** (A5):
   - `load_params` = defaults ← `bot/embedded.PARAMS[name]` ← overrides. The `config_dir`
     argument is removed; `tests/test_tier1.py` passes dicts instead.
   - `load_tables` reads `bot/embedded.TABLES` via `np.load(io.BytesIO(...), allow_pickle=False)`.
   - `active_rules` uses `bot/embedded.SPEC`. The lab can override with the env var
     **`POKERBOT_VARIANT_JSON`**, which holds the spec JSON *text*, not a path (no file read).
     `lab/players.py` sets it from `variant_path`.
   - `bot/config/*.json` and `data/` stay as the **sources** for `tools/embed_data.py`.
   - Remove the A4 allow-list. The runtime sandbox test must now **pass** (drop the xfail).
3. **`bot.py` at the repo root:** it puts its own folder on `sys.path` and calls
   `bot.main.main(["--protocol", "pokerbots"])`. Nothing else. `python3.11 bot.py` must work from
   any cwd.
4. **Packaging** (`tools/package_submission.py`):
   - Build a zip with `bot.py` at the **top level**, plus the needed `bot/` and `variant/` modules and
     `bot/embedded.py`.
   - **Fail if the zip is over 5 MB.**
   - Drop the copying of `bot/config` and `data/`.
   - The checks run on the unpacked package: imports, the sandbox audit (A4), startup, a smoke
     match over the real protocol, timing, and memory.
   - Startup (launch → ready, including imports) must be under **1.0 s** here (the 5 s limit, with a
     2× slower server and margin).
5. **Timing** (`bot/timing.py`, `bot/main.py`). **Red flag from Phase C:** in a 400-hand
   tier2-vs-tier2 match one bot used ~34 s of its 60 s bank on this laptop. On a server ~2× slower
   that is past the bank, i.e. a forfeit, unless the budget adapts in time. Fix the budget so the worst
   realistic case fits, not the average:
   - Hard limit per reply = `min(per_response_s * 0.3, 1.5 s, budget * hard_mult,
     hard_bank_frac * bank_left)`, where `per_response_s` comes from `init` (default 5).
   - Budget = (`time_left` from the engine, minus the reserve) / (hands left × expected decisions per hand),
     / 2 (server speed).
   - Count the discard as a decision: `decisions_per_hand` becomes ~3.5. Measure the real average in
     the lab and set it.
   - Emergency mode (Tier 0, i.e. check/fold plus `fallback_discard`) when the bank is below
     `max(1 s, 5 %)`.
   - Never hardcode 400/60: everything comes from `init`.
   - Wall-clock kill: our own time is bounded by the bank (60 s / 150 s), well under 180 s / 450 s.
     Startup and init warm-up count toward the wall clock, so keep warm-up under 0.5 s.
   - Measure where Tier 2's time goes (decisions per hand, ms per street, discard ms) in the
     self-play match, and against `maniac`/`all_in` (the most decisions). Cut samples
     (`max_samples`, `rollout_worlds`, `pimc_worlds`) before cutting logic.
   - Add a **slow-machine test**: run the 400-hand self-play match with the timer told the machine is
     2× slower (scale measured time by 2 in `TimeManager`, test-only flag). The bank must never run
     out, and emergency mode must not trigger before hand 380.
6. **Endgame lock** (`bot/brains/tier2.py:lock_margin`): it uses the rules' blinds and
   `state.hands_remaining`.
   - Test it with `discard_holdem` at 400 and 1000 hands.
   - Test that it never locks with a negative or zero lead.
   - Lock only while we lead (net chips decide the match).
7. **Benchmarks:**
   - `lab.timing_bench --variant variant/catalog/discard_holdem.json --hands 400` and
     `--hands 1000 --bank 150`, over the real protocol, as a subprocess, against `tier2` (self-play),
     `maniac` and `starter`.
   - Projected 2× time must be **≤ 50 % of the bank**, and the worst single reply **≤ 0.5 s**.
   - `lab.memory_check` peak must be ≤ 500 MB.
8. **Upload #1:** build the zip and hand it to the user to upload on Unstop (Claude cannot
   upload). Record the zip hash and date in `docs/SUBMISSIONS.md`.

### Tests
- The sandbox runtime test passes.
- The embed-is-current test passes.
- The package test builds, is ≤ 5 MB and passes all checks.
- Timing:
  - the hard limit is never above 1.5 s;
  - the budget follows `time_left_ms`;
  - emergency mode triggers at a low bank.
- Lock tests at 400 and 1000 hands.
- The slow-machine self-play test (step 5).

### Done when
The Phase C review is reported, the zip passes every check, the numbers are in the report, and the user has uploaded it (a valid
upload exists).

---

## Phase E — Tier 2 on the real game, with the lessons from the LLM bots

Goal: a stronger Tier 2 that is a good bot in its own right. It is upload #2, the fallback if
Tier 3 doesn't ship, and the bar Tier 3 has to beat. Three parts: play the real game well (discard,
tables), plug the measured river leak, and take the ideas the Hold'em LLM bots did better
(`docs/reports/OPPS_ANALYSIS.md` section 8). **Ideas only, written in our own code. Never copy from
`Opps/`, and never reuse their Hold'em numbers.**

### Check first
- Review Phase D (zip, timing numbers, the slow-machine test) before building.
- `bot/brains/tier1.py:Tier1Brain.special` calls `bot/sim/policies.py:decide_special` (PIMC over
  hidden worlds). Check that it handles `discard` with simultaneous order and public visibility.
- `bot/sim/inference.py` has decision kind `"discard"` (it weights opponent hands by the discard
  they made). Check it is fed by the Phase C messages (opponent special + reveal).
- `lab/precompute.py` builds `data/<variant>/` tables for any hole size (`bot/sim/canonical.py`
  handles 3-card classes).
- `bot/opponent.py:OpponentModel` and `bot/brains/tier2.py:Tier2Brain.adjusted`: what Tier 2
  already tracks and how it shifts thresholds. Extend them; don't duplicate them.
- The leak: `logs/accounting_tier2_vs_opp3_10pairs.txt` (Hold'em) and the river-showdown lines in
  `logs/discard_holdem_tier2_vs_bots.txt`.

### Evaluation pool for this phase
Phase F's LLM bots may not exist yet, so E measures on what is available:
- `tier1`, `random_legal`, `calling_station`, `tight`, `maniac`, `all_in`, `starter`;
- `opp1`–`opp4` (Hold'em bots on a makeshift adapter, so indicative only; opp3 and opp4 are the
  only current bots that beat Tier 2);
- the Phase F **training** bots, if they already exist. Never the held-out ones.

**Keep rule for every step:**
- `lab.eval tier2:variant=<json> --compare tier2` on that pool, 50 pairs, locks off;
- keep a change only if the pool aggregate improves and **no opponent drops by more than 2 SE**;
- record every result (kept or dropped) in `docs/reports/TIER2_DISCARD.md`.

### Build (one commit per step, measured before the next)
1. **E1. Discard quality:**
   - the discard decision uses the full remaining hand: the best 2 cards against the inferred
     opponent range, with turn and river to come;
   - the opponent's revealed discard counts as both a dead card and inference evidence;
   - a cheap fast path for obvious cases: a pair plus a kicker, or a made flush/straight using 2
     hole cards.
   - **Ablation:** PIMC discard vs `fallback_discard` (lowest card) vs "keep the best pair of cards
     by preflop equity", 50 pairs each. Keep PIMC only if it wins by more than 2 SE.
2. **E2. Tables:**
   - `lab.precompute --variant variant/catalog/discard_holdem.json` gives start-of-hand classes
     (3-card, suit-isomorphic, ~1,755 classes) and equities vs random and vs a top range.
   - Run it overnight if needed. It is resumable.
   - Embed it (A5) and check the size guard. Faster preflop also frees time for later streets.
3. **E3. Opponent stats module, `bot/strategy/oppstats.py`** (built here so Tier 3 reuses it, not in G):
   - per-spot Beta counts with a **population prior** (LLM bots: value-heavy bettors, over-callers),
     prior strength ~15 observations;
   - a spot changes play only after **≥ 20 samples**, and each shift is capped at **±15 points**;
   - E uses three spots: the **river/turn bluff index**, **fold rate per bet-size bucket**, and
     fold-to-bet per street. Phase G adds the rest.
   - Unit tests: the prior dominates early, the gate holds below 20 samples, the cap holds.
4. **E4. River bluff-catch stat** (idea from opp3's `river_bluff`; it aims straight at the
   measured leak):
   - after every showdown where the opponent bet or raised the turn or river, record whether
     their hand was **weak**, meaning below what a value bet needs. Use the equity of their shown
     hand against the range we represented, or simply "they lost to a hand we would check".
     Pick the simplest measure that works and document it.
   - this gives the **bluff index**, the share of their shown big bets that were weak.
   - Tier 2's call rule vs a turn/river bet: the needed equity rises when the bluff index is low
     (a value-heavy bettor: fold more bluff-catchers) and falls when it is high (an over-bluffer:
     call wider). Use a CONFIG slope; the default prior means "value-heavy", per the leak.
   - **Accounting check:** river showdown losses vs opp3/opp4 must shrink, without losing more to
     folds than it saves.
5. **E5. Bet size chosen by expected value** (idea from opp4's `evaluate_bet_candidates`; its fold
   model was broken, ours is measured):
   - candidates 33 %, 66 %, 110 % of the pot, and all-in;
   - EV(size) ≈ P(fold | size) × pot + (1 − P(fold | size)) × (equity when called × final pot −
     cost). P(fold | size) comes from E3's per-size fold stats (population prior until 20 samples);
     "equity when called" = our equity vs their range narrowed by a call, from inference, or a CONFIG
     discount;
   - use it for value bets and for bluffs. To avoid tells, when two sizes are within a CONFIG margin
     of EV, pick by a seeded random draw.
   - It replaces `value_frac` / `strong_frac` / `bluff_frac` only if it passes the keep rule.
6. **E6. No awkward leftovers** (idea from opp3's `_raise_amount`): when a value raise would leave
   less than a CONFIG share (~25 %) of the resulting pot behind, raise all-in instead. Unit tests
   plus the keep rule.
7. **E7. Baselines and accounting:**
   - `lab.sparring_audit` on `discard_holdem`;
   - `lab.eval tier2 --pool <the whole E pool> --pairs 50 --locks off --report accounting,profile`;
   - Tier 2 must beat tier1, every sparring bot and `starter`. Report opp1–4 with the caveat.
8. **E8. Timing re-check:** `lab.timing_bench` at 400 and 1000 hands and the Phase D slow-machine
   test, with E1–E6 in. They must stay inside the Phase D limits.
9. **E9. CFR question:**
   - add a dated note to `docs/PART3_ROADMAP.md`: condition 4 ("a free week before the reveal") is
     now met, and the raise cap shrinks the tree, but the main reason CFR lost (coarse card
     buckets) still stands;
   - **do not start CFR work.** Ask the user.
   - **2026-10-29: the user decided.** CFR goes ahead as a separate track, Tier 4, planned in
     `docs/CFR_PLAN.md` (blueprint + live river solver + the Tier 3 adaptation layer, gate A ~3–4 Nov).
     Phase E only adds the dated note above; the CFR work itself follows `docs/CFR_PLAN.md`.
10. **Upload #2:** if Tier 2 improved, build the zip (Phase D checks) and hand it to the user.

**Not taken from the bots** (decided, don't revisit): push/fold charts (stacks reset every hand),
opp4's match-utility formula (monotone in EV, so it changes nothing), opp1's draw bonus (our
simulation already counts draws), opp3's preflop structure (that is Tier 3's job, in G2; an earlier
Hold'em test of "raise more preflop" alone made Tier 2 worse).

> **Done (2026-10-29; commits on `claude/phase-e-on-refactor-c07yie`, zip `dist/upload2_phaseE.zip`, sha256 `1baec44f…`).**
> E1 fast sampled discard and E2 embedded tables kept; smart rollouts dropped; E4 `river_bluff_slope` 0.5 kept;
> E5 `ev_sizing`, E6 `leftover_frac` and `table_range_weight` dropped (`docs/reports/TIER2_DISCARD.md`).
> E7 (50 pairs, full pool): beats every sparring bot, the starter, opp1, opp2; about even with opp3 (+0.10 ± 0.07);
> **loses to tier1 (−0.64 ± 0.24) and opp4 (−0.60 ± 0.17)**; head-to-head vs the Phase D config +0.68 ± 0.26.
> Timing needed `safety_factor` 4.5 → 5.5 (projected 2x use 37–48 %).

### Done when
- Tier 2 beats every baseline on `discard_holdem`;
- PIMC discard is shown to beat the simple discards;
- the tables are embedded;
- each of E4–E6 is kept or dropped on the numbers, recorded in `docs/reports/TIER2_DISCARD.md`;
- timing passes;
- the CFR question is in the report for the user, and upload #2 is built.

---

## Phase F — Opponent pool (the user's LLM bots)

### Setup
- The user generates bots with several LLMs, with **both PDFs attached** and this exact prompt
  (same for every model; no extra hints):

  > Build a bot for this poker competition. The two attached PDFs are the official rules and
  > protocol. It must never crash or time out, and it should win as many matches as possible.
  > Deliver a complete bot.py (or a folder with bot.py at the top level) that runs with
  > `python3.11 bot.py`, uses only the standard library, numpy and scipy, and speaks the protocol
  > exactly as specified. Give me the full code, no placeholders.

- They go in `Opps/discard/<model>/bot.py` (extra files in the same folder), committed and pushed to
  `main`. **Their code is not fixed**: crashes and protocol errors are part of what the field
  looks like.
- The user picks **2 held-out bots before any results are seen**. Write the split to
  `lab/opps/discard_pool.json`: `{"train": [...], "heldout": [...], "prompt": "<the prompt above>",
  "models": {...}, "date": "..."}`.

### Build
1. **Auto-register** every `Opps/discard/*/bot.py` in `lab/players.py` as `d_<name>`:
   `SubprocessPlayer(cmd=[".venv/bin/python", "bot.py"], cwd=<folder>, protocol="pokerbots")`.
   No wrappers, no fixes to their code. Their crashes and timeouts are data.
2. **Health check per bot:**
   - starts, finishes a 400-hand match, its errors/notices, its time used;
   - result: "would forfeit" yes/no.
3. **Baseline report** `docs/reports/DISCARD_OPPS.md` (the format of `docs/reports/OPPS_ANALYSIS.md`):
   - Tier 2 vs each **training** bot: match score with locks on (100 pairs), chips/hand with locks
     off (50 pairs), accounting, action profiles;
   - each bot's style;
   - the common pattern across bots;
   - where Tier 2 loses.
   - Held-out bots: a **health check only**. No results are read until Phase G's final check.
4. **Re-check Phase E on the real pool:** rerun `--compare` for each kept E change (E1, E4–E6) on the
   training bots. A change that now drops a training bot by more than 2 SE goes back to the user
   with the numbers; don't silently revert it.
5. `opp1`–`opp4` are retired from decisions (Hold'em bots). Keep them runnable; report them only
   as context.

### Done when
The report is committed, the E re-check is reported, and the user has seen both.

> **Status (2026-10-30), Phase F v2** (`docs/PHASE_F_V2_PROMPT.md` replaced the "user generates the bots"
> setup): the pool is built (`Opps/discard/`: conv_opp3, conv_opp4 and seven independent bots), registered
> as `d_<name>`, and healthy (`docs/reports/DISCARD_OPPS.md` section 3). **Deferred at the user's request:**
> the held-out split, the Tier 2 baseline and the Phase E re-check (section 4 of the report).

---

## Phase G — Tier 3: the "Ivey" style

> **Built (2026-10-30, branch `ccr-412db155-a836ca`; report `docs/reports/TIER3.md`).** As built:
> - `bot/brains/tier3.py` (`DEFAULTS` = the CONFIG; Tier 3 inherits Tier 2's *shipped* parameters, so
>   `"t3": false` is Tier 2), `bot/strategy/{potmath,texture,preflop,ranges}.py` (`potmath`, not
>   `math`, so the stdlib module is never shadowed), Phase G spots in `bot/strategy/oppstats.py`.
>   Tests: `tests/test_tier3.py`, `tests/test_potmath_texture.py`, `tests/test_ranges.py`,
>   `tests/test_oppstats.py`; Tier 3 cases in `tests/test_timing_slow.py`.
> - **Deviation: evaluated only against non-pool opponents** (sparring bots, starter, tier1, tier2;
>   not opp1–opp4 either, since two pool bots are conversions of opp3/opp4). The held-out split was
>   not chosen yet, so the per-step `--pool train` runs, G8 criteria 2–3 and upload #3 are still to do.
> - Two guards the plan did not have, both found by ablation (the WIP folded far too much against
>   wide, big-betting players: the preflop size-shrunk defence and the own-range MDF slice ignore
>   who bets): `eq_floor` (never fold, preflop to turn, what Tier 2's pot-odds rule calls) and a
>   gated `value_floor` (a hand Tier 2 would value-raise goes to Tier 2, with probability = how
>   far the opponent's turn/river fold rates sit below the prior, gated and capped).
>   `mdf_eq_slack` and `bluff_tilt_scale` are kept as neutral guards.
> - G7 `hide_discard`: no gain, off. The sizing A/B: texture sizes lost to Tier 2's sizes for the
>   value floor; c-bets, barrels and bluffs keep texture sizes.
> - G8 criterion 1 (locks on, 100 pairs vs Tier 2): match score 0.580 ± 0.035, met narrowly. Locks
>   off, Tier 3 wins chips vs Tier 2 but only ~0.42 of matches: re-check on the training pool.
> - Open gaps vs Tier 2: tight −2.1 ± 0.5, random_legal −2.4 ± 0.7 chips/hand (both still won 100 %).

The style, from the user's spec:
- relentless initiative;
- defend by MDF, not raw equity;
- floats;
- light 3-bets and 4-bets with blockers;
- small high-frequency bets on paired/dry boards;
- size by board and range, never by hand strength;
- mixed (randomised) decisions;
- capped live adaptation.

It is built on top of **Phase E's Tier 2**: its equity, inference, PIMC discard, endgame lock,
legality checks, `oppstats` (with the bluff index) and EV sizing, **all kept**. The bar is that
improved Tier 2, not the old one. No CFR, no solving at runtime.

**A known tension, decided up front.** The style says "defend by MDF / call down more", but the
measured leak is losing big river showdowns to value-heavy bettors. Resolution: MDF sets the
*base* continue range only on the flop and turn. River bluff-catching follows the bluff index
(E4), whose prior is value-heavy, until ≥ 20 samples say the opponent over-bluffs. Do not let MDF
override that on the river.

### Structure (small modules, all numbers in one CONFIG)
- `bot/brains/tier3.py`: `Tier3Brain(Tier2Brain)` and `DEFAULTS` (the CONFIG).
  - Every number below lives in `DEFAULTS`, so `lab.eval BRAIN:variant=json` and sweeps can change it.
  - Register `"tier3"` in `bot/main.py:BRAINS`. The default brain stays `tier2` until G8.
- `bot/strategy/math.py`:
  - `required_fold(bet, pot) = bet/(pot+bet)`;
  - `mdf(bet, pot) = pot/(pot+bet)`;
  - `bluff_share(bet, pot) = bet/(pot+2*bet)`;
  - `spr(stack, pot)`.
  - Unit tests with the spec's numbers: 33 % → MDF 75 %, bluff share 20 %; 66 % → 60 %;
    75 % → bluff share 30 %; 100 % → 50 % / 33 %.
- `bot/strategy/texture.py`:
  - board texture: paired, monotone/two-tone, connected, high card, dry/wet score;
  - draw features of our 2 (post-discard) or 3 (pre-discard) hole cards with the board: flush
    draw, open-ended/gutshot, backdoors, overcards.
  - Pure, NumPy-free where possible, unit-tested on hand-picked boards.
- `bot/strategy/ranges.py`: our **own range** percentile of a hand on this board.
  - Sample the hands we would have played this way (preflop class percentile from the tables,
    filtered by our line), and rank our hand among them by equity.
  - This is what "continue with the top MDF slice of our range" uses.
- `bot/strategy/oppstats.py` (**exists from E3**; extend it, keep its prior/gate/cap rules): per-spot Beta counts.
  - Add the spots: fold-to-open, raise-vs-limp, 3-bet %, fold-to-3-bet, c-bet %, fold-to-c-bet,
    check-raise %, turn/river bet %, fold-to-turn/river bet, **bluff index** (the share of their
    bets later shown at showdown as weak, i.e. below the 40th percentile of their range).
  - Priors are the population of LLM bots (value-heavy bettors, over-callers), with strength
    ~15 observations.
  - A spot deviates from base only after **≥ 20 samples**, and each shift is capped at **±15
    points**.
  - The **discard is a new information spot**: their revealed discard narrows their range (inference
    does the maths), and their discard *habits* (e.g. breaking pairs, keeping suited cards) are
    tracked as a stat.
- Mixing: every decision draws from probabilities with the brain's seeded `pyrng`. No hard
  thresholds at the edges: use a linear blend over a small band around each cutoff.

### Preflop (3 hole cards)
The Hold'em 169-class charts don't apply. Build everything from the **precomputed 3-card class
table** (Phase E):
- **Strength** = the class's equity percentile vs a random hand (best 2 after the discard is built
  into the precompute).
- **Playability** = computed from features: the best suited pair among the 3 cards, connectedness,
  a pair, an ace with a suited card.
  This replaces Hold'em's "suited wheel aces, suited connectors" bluff set. Compute it; do not
  hand-translate hand names.
- **Button first in:**
  - raise to 2.5 bb (5 chips) ~70 %: the top strength percentiles plus the high-playability lower
    hands;
  - limp ~25 %: middle strength, low playability, plus a few traps from the top;
  - fold ~5 %: the bottom.
  - Adaptation: opponent raises our limps > 40 % → limp ~5 %. Folds to opens > 50 % → raise ~100 %;
    < 25 % → raise ~60 % at 3 bb.
- **BB vs a 2.5 bb raise:**
  - defend ~70 % (call + 3-bet);
  - 3-bet ~15–18 % to ~9 bb: top ~8 % for value plus high-playability bluffs;
  - wider vs min-raises, tighter vs 3 bb+.
- **BB vs a limp:** raise ~40 % to 4 bb (value + playable), else check.
- **Button vs a 3-bet:** continue ~60 %, mostly call. 4-bet ~8 % at ~2.2× the 3-bet: the top ~3 %
  plus high-playability bluffs. 5-bet = all-in. Fold the rest.
- Opponent 3-bets > 20 % → widen calls and 4-bet bluffs. < 8 % → fold more.
- Remember the raise cap: preflop allows only 3 voluntary raises, so "4-bet" is the last raise and
  the 5-bet shove is only possible if the cap allows. Check `raises_left` and never plan a raise the
  cap forbids.

### Flop (3 hole cards, before the discard)
Our equity is the best-2-after-discard equity (Tier 2's sim already models the discard step).
- **We raised preflop (in position):**
  - c-bet ~65 % overall;
  - 33 % pot on dry, paired and high-card boards (range-bet ~80 %+);
  - 66–75 % pot on wet boards (polarised);
  - check back with medium hands on boards that favour the caller (low and connected);
  - bluff candidates are 15–40 % equity hands (draws, gutshots, overcards).
- **We are BB (out of position):**
  - vs a c-bet, continue at **MDF × 0.9–1.0** of our range, taking the top slice by own-range
    percentile;
  - check-raise ~10–12 % (strong value, strong draws, gutshot + overcards);
  - lead < 5 %.
- **Floats (in position):** call with no showdown value but outs/backdoors vs out-of-position bets
  when the opponent's turn-check rate is high. Mark `floated=True` on the hand.

### Discard
Use Tier 2's PIMC discard. Then update the hand plan from both revealed discards, e.g. the
opponent discarded a card of the flush suit → their flush-draw weight drops (inference does this).
Add an option to choose between equal-EV discards to **hide our hand**: prefer the card whose reveal
says least about our holding. Gate it behind a CONFIG flag and A/B it.

### Turn
- Barrel polarised (66–75 %): value, draws > 25 % equity, and a few blocker bluffs.
- Check medium hands.
- Floated hands bet ~65 % when checked to, rising toward 85 % if fold-to-turn > 50 %.
- Facing bets: MDF × the bluff-index adjustment.

### River
- Value-bet the top ~1/3 of our range at 66–100 % (a rare 125 % with the nuts).
- Bluff with missed draws and no-showdown hands that block their calling range, at the
  `bluff_share` ratio.
- Medium hands check and call as bluff-catchers per MDF × bluff index.
- **The Phase 0 finding matters here.** Tier 2 lost mostly in river showdowns vs the strongest
  Hold'em bot (`logs/accounting_tier2_vs_opp3_10pairs.txt`). The population prior must therefore
  be "value-heavy river bettor": fold bluff-catchers to big river bets until the bluff index
  (≥ 20 samples) says otherwise. Watch river showdown losses in the accounting at every step.

### Adaptation rules (after the ≥ 20-sample gate, capped)
- **Value-only bettor** (low bluff index): fold bluff-catchers to big bets, value-bet thinner and
  bigger, bluff less.
- **Over-bluffer:** call down wider, check-raise more, stop folding to c-bets.
- **Fold-to-c-bet > 55 %:** c-bet ~100 % small. **< 35 %:** value and real draws only.
- **Calling station:** stop bluffing, value-bet three streets.

### Time
- Preflop is a table lookup.
- Postflop, budget = `bank_left / hands_left × 0.8`, floor 20 ms, capped by Phase D's hard limit.
- Flop equity ~300–600 samples, turn ~600, river exact where cheap. Cache per hand.
- Fast path for the nuts and for trash.
- Cut samples before cutting logic. Run `lab.timing_bench` after every G step.

### Build order (each step = one commit, measured before the next)
1. **G1:** review Phase F, then CONFIG + `math.py` + `texture.py` + the new `oppstats` spots, with
   unit tests. Tier 3 = Tier 2 behaviour (no change yet). Check it plays like Tier 2 on 2 pairs.
2. **G2:** preflop (button and BB policies, 3-bet/4-bet, raise-cap aware). Ideas from opp3's
   `preflop()` (a percentile cutoff that moves with the opponent's fold-to-open and 3-bet rates; BB
   iso-raises; light 3-bets vs openers who fold to 3-bets), in our own code with 3-card tables.
3. **G3:** flop as the preflop raiser (c-bet frequencies and sizes by texture, check-backs).
4. **G4:** flop defence (MDF continue, check-raise, floats).
5. **G5:** turn and river (barrels, floats, value/bluff ratios, bluff-catching with the bluff index).
6. **G6:** live adaptation (oppstats gates and caps wired into G2–G5).
7. **G7:** discard-hiding option (A/B).
8. **G8:** ship decision.

For each step:
- run `lab.eval tier3 --pool train --pairs 50 --locks off --report accounting,profile` and
  `--compare tier2 tier3`;
- keep the step only if the aggregate improves and **no training opponent drops by more than
  2 SE**;
- record the numbers in `docs/reports/TIER3.md`;
- if a step makes things worse, set its CONFIG to Tier 2's behaviour and move on (don't spiral).

**Sizing in Tier 3.** The style says "size by board and range, never by hand strength", while E5
picks the size per hand by EV. Tier 3 uses texture-based sizes (G3/G5) by default, with a CONFIG
switch to E5's EV sizing. A/B them in G5 and keep the winner.

### Action-profile targets (`lab.eval --check-profile`)
- Button open raise / limp / fold: 65–75 / 20–28 / ≤ 7.
- BB vs a limp, raise: 35–45 %.
- Facing a preflop raise: fold 25–30 %, 3-bet 15–18 %.
- Flop c-bet as the raiser: 60–70 %. Flop fold vs a bet: 30–45 %.
- River bet: 35–45 %. River fold vs a bet: 40–50 %.

These are style targets, not goals in themselves. **Winning matches beats hitting a target**:
when they conflict, the eval numbers win, and the report says so.

### G8: ship decision
`DEFAULT_BRAIN = "tier3"` only if all of these hold:
1. Tier 3 beats Tier 2 head-to-head (100 pairs, locks on, match score > 0.5 by more than 2 SE).
2. It is better on the training pool (locks on and off).
3. One run on the **held-out** pool (`--final`, 100 pairs) is not worse than Tier 2.
4. Timing and memory are within the Phase D limits at 400 and 1000 hands.

If it ships: **upload #3**. Otherwise the Phase E Tier 2 ships, and Tier 3's best individual
behaviours may be ported into Tier 2's CONFIG one at a time, with the same checks.

---

## Phase H — Problem Statement (1 Nov) and final freeze

### On 1 Nov (insert between phases as soon as it is released; it may land during D or E)
- Save it as `docs/rules/problem_statement.pdf` and diff it against `docs/rules/SUMMARY.md`.
- Settle the showdown rule (any 5 of 7?), and every edge case and worked example. Turn each
  worked example into an A1 scenario or A2 transcript.
- Update `discard_holdem.json`, the tests, `CLAUDE.md` and `SUMMARY.md`.
- Update any provisional limit that changed: RAM, banks, per-reply limit, wall clock, C.

### Nov 13–15: freeze
- No strategy changes after Nov 13.
- Full test suite plus `-m slow`, packaging checks, timing at 400 and 1000 hands, a memory check
  and a 2,000-hand fuzz on the **final zip**.
- The user uploads the final zip and records its hash in `docs/SUBMISSIONS.md`.
- Keep the previous zip as the fallback.
- Last check, on a fresh clone of `main`: `python3.11 bot.py` against the starter bot through the
  real protocol for a full 400-hand match.

---

## Risks to watch

- **Time bank (open, Phase D):** one Tier 2 used ~34 s of 60 s locally in self-play. Projected on a
  2× slower server that forfeits. Phase D's slow-machine test is the guard; re-run it after every
  E and G step.
- **The river leak vs the style (E4, G):** "call down more" is exactly what lost chips. The bluff
  index decides river calls, not MDF.
- **Stale GitHub:** sessions only see pushed work. Merge and push `main` after every phase, and
  start each phase by reviewing the last one.
- **The Hold'em bots mislead:** opp1–4 numbers on `discard_holdem` are indicative only. Decisions
  from F onward use the Discard Hold'em LLM pool.

- **Opponent discard index and missing flop action (Phase C): resolved.** The dead-card reconstruct
  test and the round-trip kit cover them; D1 re-checks them on more seeds.
- **5 s per reply:** the current hard-deadline maths allows 15 s. Phase D fixes it, and a test
  guards it.
- **File reads:** the bot must not read config, tables or the spec from disk on the server.
  Phase D's runtime audit test is the proof.
- **Over-fitting:** a few LLM bots are a small sample. The held-out split plus the "no opponent
  drops by more than 2 SE" rule are the guards.
- **Time:** Tier 3 adds logic per decision. Watch the worst reply and the projected 2× bank after
  every G step.
