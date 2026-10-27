# CLAUDE.md — Synergy PokerBots toolkit

**Main repo: `~/Desktop/pokerbots_synergy2`** (since 2026-10-25). The original
`~/Desktop/pokerbots_synergy` is an untouched archive: never edit or commit there.

Variant-agnostic poker bot toolkit. The real variant is revealed on day 1 of the
competition; we then have ~3 days to fill in the variant-specific parts. Read this
file before changing anything.

## Hard constraints for the submitted bot (`bot/`)

- **Python 3.11 only.** Stdlib + NumPy (+ SciPy only if truly needed, imported lazily).
  No other imports in `bot/` — a test enforces this.
- **Resources:** 1 vCPU, 1 GB RAM, read-only filesystem, no network.
  The bot never writes files and never imports network modules.
- **I/O:** stdin/stdout with the engine. **stdout = actions only**, flushed after each one.
  All logging/debug goes to **stderr**.
- **Time bank:** ~60 s cumulative per 400-hand match (~150 ms/hand, ~20–40 ms/decision).
  Assume the server is ~2× slower than a laptop. Timeout or crash = forfeit.
  Finals may be ~1000 hands: read hand count and bank from match info, never hardcode.
- **Scoring:** duplicate deals (seats swapped). Match win = 1, draw = 0.5. Chip margin is
  only a capped tie-breaker → we optimise for *winning matches*, not max chips.
- **Data files:** `.npy` files may or may not be allowed. Every data dependency is
  optional with a working in-memory fallback. Nothing is written to disk at runtime.
- **Code review:** code is reviewed manually — clean, commented, original. No copied
  third-party poker code.

## Architecture rules

- A variant is a JSON spec (`variant/spec.py`; presets in `variant/catalog/`; the bot plays
  `variant/active.json` or `$POKERBOT_VARIANT`). It compiles into a **hand program** of step
  plugins (`bot/game/compile.py`). `variant/rules.py` GameConfig is the legacy fallback.
  Never hardcode Hold'em numbers (2 hole cards, 5 board cards, 3/1/1).
- `bot/game/` = the rules, pure and submit-safe (state, steps, payoffs, scoring). The lab
  engine and the bot's simulator (`bot/sim/`) run the same code. Information only flows
  through `state.emit(..., visible=...)`; hidden-information correctness is tested.
- Wire formats live only in `bot/protocol.py` (neutral messages) and `bot/protocols/`
  (one adapter per format). Brains see only neutral objects (state, legal actions, budget).
- `lab/` is offline tooling, never submitted; it may use anything in the dev venv.
- Safety, three layers: (1) brain in try/except → Tier 0 on error; (2) every action
  validated + clamped before sending; (3) hard deadline / emergency mode → Tier 0.
  The main loop never lets an exception escape (clean exit on EOF only).
- macOS uses `spawn` for multiprocessing: `if __name__ == "__main__":` guards and
  picklable top-level worker functions.

## Phases

1. Repo setup · 2. Bot skeleton · 3. Generic evaluator · 4. Equity engine ·
5. Rules engine + duplicate harness · 6. Sparring bots + version loader ·
7. Tier 1 bot · 8. Tier 2 bot (+ endgame lock) · 9. Test tooling (fuzz, timing, memory, sweep).
Part 2 (universal toolkit): 10 hand programs · 11 variant spec + catalog · 12 deck/evaluator
plugins · 13 card steps · 14 betting structures · 15 payoffs/side mechanics · 16 generic
decision layer · 17 inference · 18 precompute · 19 protocol adapters · 20 day-1 toolkit ·
21 rehearsal drills · 22 MCCFR-lite (stretch).
Part 3 (`docs/PART3_ROADMAP.md`): 23 CFR diagnosis (done) → **CFR is a no-go**: Tier 2 is
the shipped bot; CFR code stays lab-only (`lab/cfr/`), out of `bot/` and the package.
Next: reduced 24 (tournament simulator, hackathon-day bot + realistic opponents, training /
held-out pool split, tournament-points report; no LBR), then 21 rehearsals with
self-written variants. Phases 25–32 are not pursued.

Each phase ends with: all tests green on 3.11, a short report (what/tests/numbers),
the exact list of files that change when the variant is revealed, and a commit
`phase N: ...`. Stop after each phase and wait for OK.

## Working rules

- Simple and robust over clever. Never let an exception reach the engine.
- Write tests as you go; never move on with failing tests. Tests are seeded/deterministic.
  Slow tests are marked `@pytest.mark.slow` (run with `-m slow`).
- Type hints on public functions, small modules, useful comments.
- Run tests: `.venv/bin/python -m pytest -n auto` (slow: `-m slow`; another wire format:
  `POKERBOT_PROTOCOL=json`).
- If the spec is ambiguous, pick the simplest reasonable option and note it in the
  phase report. Only stop to ask if it would be expensive to undo.
- Keep replies short: what was built, test results, what's next.

---

## Team notes (from the original PokerBot repo setup, ariv-IIITB, 2026-10-20)

Kept verbatim below. Where it differs from the sections above (for example the "Layout"
and "Commands" placeholders), the sections above describe the code as it actually is.

### CLAUDE.md: Pokerbots bot

2-person team. Python bot. Deadline: Nov 15, 23:59 IST.

#### Hard constraints (from the organisers)
- Python 3.11. Standard library, NumPy, and SciPy only. No pip at runtime.
- 1 vCPU, 1 GB RAM, read-only filesystem, no network.
- Time bank: cumulative per match, about 60 s for 400 hands (roughly 0.15 s per hand on average), with a hard wall-clock kill. A crash or an exhausted bank forfeits the match.
- The bot talks to the engine over a fixed stdin/stdout protocol. Read the starter code for the exact format.
- All matches use duplicate deals: every deal is played twice with seats swapped.
- Stage 1: Swiss, 6 rounds of about 200 duplicate deals (400 hands). Win 1, draw 0.5, loss 0.
- Stage 2: top 32, round-robin, about 500 duplicate deals each, scores reset.
- Tie-breaker: capped chips per hand. Check the rules for the cap before optimising for margin.

#### Approach
1. **Strength first.** Build the strongest bot you can inside the hard constraints. Do not weaken the design for speed worries that tuning can fix later.
2. **Some limits are design limits, not tuning limits.** Memory (1 GB), the time bank, and the library list decide which algorithms are even possible, so they apply from day one. At about 0.15 s per hand on one core, heavy search or solving cannot run online. Train and precompute offline, ship compact tables in the repo (the filesystem is read-only, so the bot cannot write or cache anything), and keep online decisions cheap lookups plus light computation. Any ML model must run in NumPy only.
3. **Spend the time bank on purpose.** The bot tracks its own remaining time and switches to a cheap fallback policy when the bank runs low. Never run out. Measure per-hand time and peak memory; never guess either.
4. **Never crash.** Wrap the decision path so any exception returns a safe legal action. A crash forfeits the match.
5. **Then fit.** Once the strong version works, profile and cut it to the limits. Trade strength for speed only where measurements say so, and state what was traded.
6. **Read the rules yourself.** On the first session, read the rules and starter code in the repo, fill in "Open questions" and "Commands" below from them, and ask me only for what you cannot find. Do not guess.

#### Open questions (find in the rules or starter code; do not guess)
- Does import and table-loading time count against the time bank?
- The cap in the capped chips-per-hand tie-breaker.
- Game variant and engine API details; maximum submission size.
- Entry point:

#### Commands (fill in from the starter repo, then keep current)
- Run one match:
- Run match batch vs opponent pool (duplicate deals):
- Tests:
- Resource check (time bank and memory):

#### Layout
- `bot/`: submission code and precomputed tables only
- `tools/`: match runner, opponent pool, hand-history logger, offline training and table-building scripts
- `opponents/`: simple baselines (always-call, always-raise, tight-passive, random) and frozen snapshots of our own earlier versions
- `tests/`: hand evaluator and match runner tests
- `logs/`: hand histories from matches

#### Rules
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

#### Decisions made (do not re-litigate)
- 2026-10-20: strength first, then fit; memory, time bank, and library list are design constraints from day one.

#### Lessons
- (one line per solved bug or gotcha)

#### Agent skills

##### Issue tracker

Local markdown: issues live as files under `.scratch/<feature>/` in this repo. See `docs/agents/issue-tracker.md`.

##### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
