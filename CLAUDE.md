# CLAUDE.md — Synergy PokerBots toolkit

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

- `variant/` holds **everything variant-specific** (`rules.py` GameConfig + hooks,
  `evaluator_hook.py`). Engine, equity and bots read street structure from GameConfig;
  never hardcode Hold'em numbers (2 hole cards, 5 board cards, 3/1/1).
- `bot/protocol.py` is the **only** bot file that knows the wire format. Brains see only
  neutral objects (state, legal actions, time budget).
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

Each phase ends with: all tests green on 3.11, a short report (what/tests/numbers),
the exact list of files that change when the variant is revealed, and a commit
`phase N: ...`. Stop after each phase and wait for OK.

## Working rules

- Simple and robust over clever. Never let an exception reach the engine.
- Write tests as you go; never move on with failing tests. Tests are seeded/deterministic.
  Slow tests are marked `@pytest.mark.slow` (run with `-m slow`).
- Type hints on public functions, small modules, useful comments.
- Run tests: `.venv/bin/python -m pytest`.
- If the spec is ambiguous, pick the simplest reasonable option and note it in the
  phase report. Only stop to ask if it would be expensive to undo.
- Keep replies short: what was built, test results, what's next.
