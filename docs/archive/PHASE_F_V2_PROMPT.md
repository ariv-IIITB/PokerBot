# Phase F v2: the Discard Hold'em opponent pool (prompt for Opus)

Paste this to Opus, or just say: "Read `docs/PHASE_F_V2_PROMPT.md` and do it."

---

You are working in `ariv-IIITB/PokerBot` on the Synergy Pokerbots toolkit. Read, in this order:
`CLAUDE.md`, `docs/STATUS.md`, `docs/PHASE_E_DONE_HANDOFF.md`, `docs/rules/SUMMARY.md` (then
`docs/rules/rulebook.pdf` and `protocol.pdf`), and "Phase F" in `docs/PART4_PLAN.md`. This task
**replaces the original Phase F plan** (where the user would generate the LLM bots themselves).
Call it **Phase F v2**. Work on a new branch off `main`, commit in logical steps, push the branch,
and **stop for the user's review at the end. Do not merge to `main` yourself.**

## Why

Tier 2 is tuned against Hold'em bots (`Opps/opp1`–`opp4`) running through a makeshift adapter. Those
numbers say little about the real field: Discard Hold'em bots that other teams (and their LLMs)
will submit. We need a **pool of realistic Discard Hold'em opponents (2 converted + as many new ones as needed for coverage, at most 12 in all)** that speak the real
protocol, to (a) measure Tier 2 honestly, (b) re-check the Phase E changes, and (c) give Phase G
(Tier 3) a training set and a held-out set.

## The task

### 1. Pick the two useful old bots from the evidence

The user uploaded four bots (`Opps/opp1`–`opp4`) and says only two were useful. Decide which two
by reading the logs and reports, not by guessing: `docs/reports/OPPS_ANALYSIS.md`,
`logs/discard_holdem_tier2_vs_bots.txt`, `logs/tier2_vs_opps_*`, `logs/accounting_*`, `logs/profile*`,
`logs/e7/full.txt`, and `docs/reports/TIER2_DISCARD.md`. Expected, but confirm: **opp3** (the only one
that beat Tier 2 on Hold'em: bluffs, iso-raises limps, working opponent stats, preflop structure) and
**opp4** (EV-based bet sizing, range narrowing; it still beats Tier 2 on `discard_holdem`). If the
numbers point to a different pair, use that pair and say why. Write a short "what was useful and
what was broken" note per bot into the report (section 5).

### 2. Convert those two to Discard Hold'em

Put each in `Opps/discard/<name>/` with a top-level `bot.py` (extra files allowed in the same folder),
run as `python3.11 bot.py`. Keep the original play style, port it:
- Speak the **real protocol** (JSON lines, `docs/rules/protocol.pdf`): `init`, action and discard
  requests, `notice`s, stdout = protocol only and flushed, debug to stderr only. The old bots use an
  MIT-skeleton or `get_action(dict)` API; replace that layer.
- Handle the game: 3 hole cards, 3-card flop, **simultaneous discard of one hole card after the
  flop betting**, both discards revealed and removed from play, then turn and river with 2 hole
  cards. Their equity code must model 3-then-2 hole cards and the opponent's revealed discard
  (the discard must be a real decision, not "lowest card").
- Obey the limits in `docs/rules/SUMMARY.md`: Python 3.11, stdlib + numpy + scipy only, no file or
  network access, 60 s bank per 400 hands (read `time_bank_ms` and `total_hands`, never hardcode),
  any reply under 5 s, never crash or send an illegal action (the engine folds illegal ones).
- Fix the bugs listed in `OPPS_ANALYSIS.md` section 2 only if a good LLM-written bot would plausibly
  have gotten them right; otherwise keep the flavour but make sure the bot **runs** (opp2's import
  crash is a bug of a different kind than a weak strategy).
- Original code only inside `bot/`. These bots live in `Opps/`; **never copy anything from `Opps/`
  into `bot/`** (the originality rule in `CLAUDE.md`).

### 3. Design the pool and write the new bots, as a good LLM would

Imagine a user asks a strong LLM, with both PDFs attached, this prompt (use it verbatim as the brief,
and store it in the pool file under `"prompt"`):

> Build a bot for this poker competition. The two attached PDFs are the official rules and
> protocol. It must never crash or time out, and it should win as many matches as possible.
> Deliver a complete bot.py (or a folder with bot.py at the top level) that runs with
> `python3.11 bot.py`, uses only the standard library, numpy and scipy, and speaks the protocol
> exactly as specified. Give me the full code, no placeholders.

**You decide how many new bots to write and what kinds**, to cover as much of the plausible field as
possible. Do not default to a fixed number. First write down (in the report, section "Pool design") the
axes along which real submissions will differ, check which axes the two converted bots already cover,
and add one bot per **uncovered** corner. Axes to consider, not a checklist:
- playing style: tight vs loose, passive vs aggressive, bluff frequency, 3-bet/4-bet appetite, trappy
  slow-play vs fast-play;
- how it estimates strength: random-hand equity (the weak pattern in `OPPS_ANALYSIS.md`), Monte Carlo
  vs a weighted range, hand-strength heuristics or fixed charts, no equity at all;
- how it handles the discard: lowest card, highest pair/draw logic, sampled equity, using the
  opponent's revealed discard or ignoring it;
- sizing: fixed fractions, pot-geometry, EV-chosen, polarised vs merged;
- adaptation: none, simple stats (VPIP, fold-to-bet), range narrowing, exploiting a detected nit/station;
- engineering quality: careful time management, versus a bot that burns its bank or is near-crash-prone
  (a few weak-but-valid bots are realistic; the field has them);
- degenerate but plausible bots: calling station, always-raise/shove, min-raise grinder, pure
  check/fold nit. Cheap to write; include the ones the sparring pool lacks.

Aim for breadth over polish: each added bot must differ from the others in a way that changes how Tier 2
should play against it. Typical size is 4-8 new bots; fewer if the axes are already covered, more only if a
corner is clearly missing. Cap the total pool (converted + new) at 12, because evals are slow
(Tier 2 plays ~22 hands/s per core). Justify the final list in a table: bot, style, which axis it adds.
Each bot must answer the prompt plausibly as a capable single-shot LLM answer would (equity + pot odds,
some blind spots), not be secretly strong, and be a **complete, runnable** bot (tests or a fuzz run
in its folder are welcome, not required).

**Independence rule (important):** build each new bot **in a fresh sub-agent** (Agent tool) that is
given only `docs/rules/`, the prompt above, and its one-line style brief. The sub-agent must not read
`bot/`, `lab/`, `logs/`, `docs/reports/`, `Opps/` or anything about Tier 2's weaknesses. This keeps the
pool independent of our bot (otherwise we would build a pool Tier 2 happens to beat). If a
sub-agent's bot is poor, **keep it**; the real field has poor bots too. Only fix crashes and protocol
errors if the bot cannot finish a match at all, and say so in the report.

Names: `Opps/discard/<name>/bot.py`, e.g. `conv_opp3`, `conv_opp4`, `new_<style>`.

### 4. Wire them into the lab

- Auto-register every `Opps/discard/*/bot.py` in `lab/players.py` as `d_<name>`:
  `SubprocessPlayer(cmd=[<python>, "bot.py"], cwd=<folder>, protocol="pokerbots")`. No wrappers around
  their code; their crashes and timeouts are data.
- **Health check per bot** (`lab/` tool, e.g. `lab/pool_health.py`): starts within 5 s, finishes a
  400-hand match against the starter bot and against Tier 2 (locks on, 10 pairs), counts errors,
  illegal actions, notices, max reply time, bank used, and says "would forfeit" yes/no. Add a test
  that runs each bot for a few hands over the real protocol.
- Make sure `lab.eval --pool d_<name> ...` and `--pool train` / `--pool heldout` work
  (`lab/opps/discard_pool.json`, see `lab/eval.py:_pool_file`).

### 5. Gate: ask the user for the held-out split

When the bots exist and pass the health check, but **before running any Tier 2 vs pool matches**,
stop and ask the user (AskUserQuestion) which bots are held out (about a third of the pool, at least 2; propose a number, they decide). They pick before seeing
any result. Write `lab/opps/discard_pool.json`:
`{"train": [...], "heldout": [...], "prompt": "<the prompt above>", "models": {name: "how it was made"},
"date": "..."}`. Held-out bots get the health check only; nobody reads their results until Phase G's
final check.

### 6. Baseline report: `docs/reports/DISCARD_OPPS.md`

Use the format of `docs/reports/OPPS_ANALYSIS.md`. Start with the "Pool design" section (axes, coverage, the table of bots and why each was added). For each **training** bot: style (from
`lab.opps.profile`), health, Tier 2 match score with locks on (100 pairs), chips/hand ± SE with locks
off (50 pairs), accounting (`lab.opps.accounting`), where Tier 2 loses. Then: the common pattern
across the pool and the old Hold'em bots, and which of Tier 2's known weak spots (river showdown
leak; the tier1 and opp4 losses from E7) show up. Compare against `Opps/opp1`–`opp4` as context only
(they are retired from decisions).

### 7. Re-check Phase E on the real pool

Rerun `lab.eval --compare` for each kept Phase E change (fast discard, tables, `river_bluff_slope`
0.5) against the **training** bots, 30+ pairs, before and after at the same time on the same machine
(wall-clock budgets: load matters; `tools/e_eval/run_e.sh` and `head2head.py` exist). Rule from
Phase E: keep a change unless it drops a training bot by more than 2 SE. If one does, **do not
revert it silently**: report the numbers to the user.

## Rules and warnings

- Tests green on Python 3.11 (`.venv`; set up with `uv venv --python 3.11 .venv && uv pip install
  --python .venv/bin/python -r requirements-dev.txt`). Fast suite: `.venv/bin/python -m pytest -n 4`
  (one load-sensitive test, `test_tier1_beats_random_and_plays_legally`, may fail under load; rerun alone).
- Evaluations are slow (Tier 2 plays ~22 hands/s per core). Run them in the background with Monitor,
  not in the foreground; the machine has 4 cores; do not run timing checks while evals run.
- Do not run `python -m tools.embed_data` unless `data/discard_holdem/` exists (it is committed; rebuild it only if the tables change);
  otherwise it writes an empty-tables `bot/embedded.py`. This phase should not touch `bot/` at all.
- Never tune Tier 2 on the held-out bots. Never copy code between `Opps/` and `bot/`.
- If three fixes in a row fail, stop and say so.
- Commit message style: `phase F2: ...`. Push the branch (not `main`).

## Done when

- `Opps/discard/` holds the designed pool (2 converted + the new bots, with the design table in the report), all registered as `d_<name>`, all passing the
  health check (or honestly marked "would forfeit" with the reason);
- `lab/opps/discard_pool.json` has the user's held-out pick;
- `docs/reports/DISCARD_OPPS.md` and the Phase E re-check are committed, with numbers and SEs;
- `docs/STATUS.md` and the Phase F box in `docs/PART4_PLAN.md` are updated;
- the final message to the user is short: what was built, the table of Tier 2 vs each training bot,
  anything that needs their decision, and what Phase G starts with.
