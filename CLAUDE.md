# CLAUDE.md: Pokerbots bot

2-person team. Python bot. Deadline: Nov 15, 23:59 IST.

## Hard constraints (from the organisers)
- Python 3.11. Standard library, NumPy, and SciPy only. No pip at runtime.
- 1 vCPU, 1 GB RAM, read-only filesystem, no network.
- Time bank: cumulative per match, about 60 s for 400 hands (roughly 0.15 s per hand on average), with a hard wall-clock kill. A crash or an exhausted bank forfeits the match.
- The bot talks to the engine over a fixed stdin/stdout protocol. Read the starter code for the exact format.
- All matches use duplicate deals: every deal is played twice with seats swapped.
- Stage 1: Swiss, 6 rounds of about 200 duplicate deals (400 hands). Win 1, draw 0.5, loss 0.
- Stage 2: top 32, round-robin, about 500 duplicate deals each, scores reset.
- Tie-breaker: capped chips per hand. Check the rules for the cap before optimising for margin.

## Approach
1. **Strength first.** Build the strongest bot you can inside the hard constraints. Do not weaken the design for speed worries that tuning can fix later.
2. **Some limits are design limits, not tuning limits.** Memory (1 GB), the time bank, and the library list decide which algorithms are even possible, so they apply from day one. At about 0.15 s per hand on one core, heavy search or solving cannot run online. Train and precompute offline, ship compact tables in the repo (the filesystem is read-only, so the bot cannot write or cache anything), and keep online decisions cheap lookups plus light computation. Any ML model must run in NumPy only.
3. **Spend the time bank on purpose.** The bot tracks its own remaining time and switches to a cheap fallback policy when the bank runs low. Never run out. Measure per-hand time and peak memory; never guess either.
4. **Never crash.** Wrap the decision path so any exception returns a safe legal action. A crash forfeits the match.
5. **Then fit.** Once the strong version works, profile and cut it to the limits. Trade strength for speed only where measurements say so, and state what was traded.
6. **Read the rules yourself.** On the first session, read the rules and starter code in the repo, fill in "Open questions" and "Commands" below from them, and ask me only for what you cannot find. Do not guess.

## Open questions (find in the rules or starter code; do not guess)
- Does import and table-loading time count against the time bank?
- The cap in the capped chips-per-hand tie-breaker.
- Game variant and engine API details; maximum submission size.
- Entry point:

## Commands (fill in from the starter repo, then keep current)
- Run one match:
- Run match batch vs opponent pool (duplicate deals):
- Tests:
- Resource check (time bank and memory):

## Layout
- `bot/`: submission code and precomputed tables only
- `tools/`: match runner, opponent pool, hand-history logger, offline training and table-building scripts
- `opponents/`: simple baselines (always-call, always-raise, tight-passive, random) and frozen snapshots of our own earlier versions
- `tests/`: hand evaluator and match runner tests
- `logs/`: hand histories from matches

## Rules
- Reply with the action or answer first. No preamble, no recap, no apologies.
- Never guess file contents, import paths, or API signatures. Read the file or grep first.
- Quote errors exactly. For long traces, quote only the relevant lines.
- Before saying something passes, show the real command output.
- Use only the standard library, NumPy, and SciPy inside `bot/`. Offline scripts in `tools/` may use anything installed locally, but their output must load with those three.
- The match runner plays duplicate deals (each deal twice, seats swapped), like the real tournament. Report match result and chips per hand with a confidence interval and the number of deals. Never call a change an improvement from a small sample.
- Run the resource check (time bank and memory) after any change to `bot/` once fitting starts. Over 1 GB or an exhausted bank is a hard fail.
- Tests are required for the hand evaluator and the match runner, written first. Elsewhere, tests are optional.
- Use integer chip counts, never floats.
- Never run `rm -rf` on parent paths, `git push --force`, or print `.env` or key files.
- If three fixes in a row fail, stop and say so. Do not keep trying variations.
- Do not start open-ended research on a library or topic. Ask first.
- One task per chat. Commit before starting a new one.

## Decisions made (do not re-litigate)
- 2026-10-20: strength first, then fit; memory, time bank, and library list are design constraints from day one.

## Lessons
- (one line per solved bug or gotcha)

## Agent skills

### Issue tracker

Local markdown: issues live as files under `.scratch/<feature>/` in this repo. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
