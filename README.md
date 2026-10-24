# Synergy PokerBots toolkit

Variant-agnostic toolkit for the Synergy PokerBots competition. The variant-specific
parts live in `variant/` (and the wire format in `bot/protocol.py`); everything else is
generic. See `CLAUDE.md` for the competition constraints and working rules.

## Setup

Requires Python **3.11** (the competition runtime).

```bash
brew install python@3.11            # if python3.11 is not installed
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Runtime dependencies of the submitted bot: `numpy` (and `scipy`, optional).
`pytest` is dev-only.

## Tests

```bash
.venv/bin/python -m pytest              # fast suite (default)
.venv/bin/python -m pytest -m slow      # slow suite only
.venv/bin/python -m pytest -m ""        # everything
```

## Layout

| Path | Purpose |
|------|---------|
| `variant/` | ★ Variant-specific: `rules.py` (GameConfig + hooks), `evaluator_hook.py` |
| `bot/` | The submitted bot (stdlib + numpy only) |
| `lab/` | Offline engine, harness, sparring bots, fuzz/timing/memory/sweep tools |
| `snapshots/` | Frozen copies of past bot versions for sparring |
| `docs/` | Project docs (e.g. `POKERBOTS_BIBLE.md`) |
| `tests/` | pytest suite, one file per module |

## Running the bot / harness / tools

Bot (reads the engine on stdin, writes actions on stdout, logs on stderr):

```bash
.venv/bin/python -m bot.main                 # default brain
.venv/bin/python -m bot.main --brain tier0   # pick a brain from bot/main.py BRAINS
.venv/bin/python -m bot.main --verbose       # extra stderr logging
```

The wire format is a placeholder defined in `bot/protocol.py` (the only file to
rewrite once the real protocol is known).

Evaluator benchmark: `.venv/bin/python -m lab.bench_evaluator`
Equity benchmark: `.venv/bin/python -m lab.bench_equity`

_Harness (phase 5) and tools (phase 9) are documented as they land._
