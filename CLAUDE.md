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
