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

## Variants

A variant is a JSON spec (`variant/spec.py` documents every field; presets live in
`variant/catalog/`). The bot plays `variant/active.json` if present (or `$POKERBOT_VARIANT`),
otherwise the built-in Hold'em config. Specs compile into a *hand program* of step plugins
(`bot/game/`), shared by the bot and the lab engine.

```bash
.venv/bin/python -m lab.random_variant --seed 3 --count 2 --supported   # random valid specs
.venv/bin/python -c "from variant.spec import VariantSpec; from bot.game.compile import compile_spec; \
  print(compile_spec(VariantSpec.load('variant/catalog/omaha.json')).describe())"
```

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

Duplicate harness (each seed played twice with seats swapped, parallel over cores):

```bash
.venv/bin/python -m lab.harness tier0 random_legal maniac --seeds 20 --hands 400   # A vs each
.venv/bin/python -m lab.harness tier0 tier0 --subprocess   # A runs as a real bot process
```

Sparring brains (lab only): `random_legal`, `all_in`, `calling_station`, `tight`, `maniac`.
Run any of them as a protocol bot: `.venv/bin/python -m lab.run_brain maniac`.

Snapshots of past versions (run as subprocess bots):

```bash
.venv/bin/python -m lab.versions create v1               # from the working tree
.venv/bin/python -m lab.versions create v0 --ref <tag>   # from git
.venv/bin/python -m lab.versions list
```

Test tooling:

```bash
.venv/bin/python -m lab.fuzz --hands 200000                  # weird bots x example variants, all cores
.venv/bin/python -m lab.fuzz --hands 2000 --subprocess       # real bot process + junk input lines
.venv/bin/python -m lab.timing_bench --hands 400             # startup, bank used, worst decision, x2 projection
.venv/bin/python -m lab.memory_check --hands 400             # peak RSS of the bot process
.venv/bin/python -m lab.sweep tier2 lab/spaces/tier2_example.json --mode random --n 12 \
    --opponents tier1 maniac tight --seeds 8 --hands 200     # ranked parameter sweep
```

Brains: `tier0` (check/fold), `tier1` (equity vs pot odds), `tier2` (default: opponent model +
endgame lock). Hyperparameters: `bot/config/tier1.json`, `bot/config/tier2.json` (optional files).
