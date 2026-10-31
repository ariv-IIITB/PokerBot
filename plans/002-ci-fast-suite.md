# Plan 002: Run the fast test suite on Python 3.11 in GitHub Actions on every push

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 39ca8f8..HEAD -- .github/ requirements-dev.txt pyproject.toml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-track-discard-holdem-tables.md (must be DONE)
- **Category**: tests
- **Planned at**: commit `39ca8f8`, 2026-10-31

## Why this matters

Nothing runs the tests when code is pushed. The project's phases are implemented by sessions
that push to GitHub, and their reports are reviewed by hand. Commit `966b2e1` ("phase F0")
pushed a packaging guard that broke two tests in `tests/test_day1.py` on every machine, and
nobody noticed for about 30 hours (fixed in `39ca8f8`). The competition deadline is 15 Nov 2026,
and a broken submission forfeits matches. A CI job that runs the existing fast suite on push
turns "someone forgot to run the tests" into a red mark on the commit.

## Current state

- There is no `.github/` directory: no CI at all.
- The fast suite runs with `.venv/bin/python -m pytest -n auto -q`. `pyproject.toml` sets
  `testpaths = ["tests"]`, `pythonpath = ["."]` and `addopts = "-m 'not slow'"`, so slow tests are
  already excluded by default. At `39ca8f8` (with `data/discard_holdem/` present): `1103 passed, 2 skipped` in ~45 s on 4 cores.
- The setup command from `CLAUDE.md` ("Commands"):
  `uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt`
- `requirements-dev.txt` pins `numpy==2.3.4`, `scipy==1.16.2`, `pytest==8.4.2`, `pyflakes==4.0.3`, `pytest-xdist==3.8.0`.
- The tests need `data/discard_holdem/` (one packaging test fails without it). Plan 001 commits it.
  Do not start this plan until `git ls-files data/discard_holdem | wc -l` prints `6`.
- Tests spawn subprocesses (`python -m bot.main`) and load third-party bots from `Opps/`, which
  is tracked in git. No network access or secrets are needed.
- Load-sensitive tests: `tests/test_tools.py::test_timing_bench_quick` (asserts start-up < 3 s)
  and the timing tests in `tests/test_timing.py`. `docs/STATUS.md` notes that "load-sensitive
  tests can still fail under `-n auto`" on a busy laptop; they pass on rerun.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Local setup (as CI will do it) | `uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt` | exit 0 |
| Fast suite | `.venv/bin/python -m pytest -n auto -q` | 0 failed |
| YAML syntax check | `uv run --no-project --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/tests.yml')); print('ok')"` | `ok` |

## Scope

**In scope** (the only file you should create):
- `.github/workflows/tests.yml` (create)

**Out of scope** (do NOT touch):
- Any test file. Never skip, mark `xfail` or delete a test to make CI green. The project rule is
  "never move on with failing tests".
- `pyproject.toml`, `requirements-dev.txt`.
- Slow tests (`-m slow`, ~21 min). They are not part of this job.
- `lab/harness.py`, `lab/engine.py`, `lab/eval.py` and the opponent bots: the owner forbids edits there.

## Git workflow

- Work on the branch you were given; if none, create `advisor/002-ci-fast-suite`.
- One commit, e.g. `ci: run the fast test suite on Python 3.11 on every push`.
- Do NOT push or open a PR unless the operator instructed it. CI only runs once the workflow is pushed.

## Steps

### Step 1: Check that plan 001 has landed

**Verify**: `git ls-files data/discard_holdem | wc -l` → `6`. Anything else → STOP.

### Step 2: Create `.github/workflows/tests.yml`

Use exactly this content:

```yaml
name: tests

on:
  push:
  pull_request:

jobs:
  fast:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Set up Python 3.11 and dev requirements
        run: |
          uv venv --python 3.11 .venv
          uv pip install --python .venv/bin/python -r requirements-dev.txt
      - name: Fast test suite
        run: .venv/bin/python -m pytest -n auto -q
```

**Verify**: the YAML syntax check in the table prints `ok`.

### Step 3: Run the exact CI steps locally in a fresh clone

This proves that a clean checkout passes with nothing but the committed files:

```bash
D=$(mktemp -d) && git clone -q . "$D/c" && cd "$D/c" && uv venv -q --python 3.11 .venv && uv pip install -q --python .venv/bin/python -r requirements-dev.txt && .venv/bin/python -m pytest -n auto -q | tail -2; cd "$OLDPWD"; rm -rf "$D"
```

The clone holds only committed files. That is the point: it is what the CI runner will check out.
The workflow file does not need to be committed for this check.

**Verify**: the last line reads `N passed, 2 skipped` with no `failed`.

### Step 4: Commit

`git add .github/workflows/tests.yml && git commit -m "ci: run the fast test suite on Python 3.11 on every push"`

**Verify**: `git show --stat HEAD` lists only `.github/workflows/tests.yml`.

## Test plan

No new tests: this plan runs the existing suite. The check is Step 3, a fresh clone running
exactly the CI commands. After the operator pushes, the first Actions run on GitHub must be green.

## Done criteria

- [ ] `.github/workflows/tests.yml` exists, and the YAML check prints `ok`
- [ ] The Step 3 fresh-clone run ends with `passed` and no `failed`
- [ ] `git show --stat HEAD` lists only the workflow file
- [ ] `git status --short` is empty
- [ ] `plans/README.md` row 002 updated (note there that the first GitHub run still needs checking after the push)

## STOP conditions

Stop and report back (do not improvise) if:

- Step 1 does not print `6` (plan 001 is not done).
- The fresh-clone run in Step 3 fails. Report the failing test names and the `E ` lines; do not
  change tests or code to fix them.
- After the operator pushes, a test fails only on GitHub (most likely the load-sensitive
  `test_timing_bench_quick` or `tests/test_timing.py` on a 2-vCPU runner). Report it. Do not
  skip it, retry it in a loop, or lower `-n`, unless the owner decides to.
- The repo already has a CI system you did not see (for example a `.gitlab-ci.yml` or another workflow).

## Maintenance notes

- Keep the CI setup identical to the `CLAUDE.md` "Setup" command. If `requirements-dev.txt`
  changes, CI picks it up automatically.
- If a timing test turns out to flake on GitHub runners, the owner may want to run it in a
  separate job with `-n 1`. That is a decision for the owner, not for the executor.
- Deliberately deferred: a scheduled `-m slow` job (~21 min) and a job that builds
  `dist/submission.zip` with `tools.package_submission --zip --stage2`. Both are worth adding
  once the fast job is stable.
- `actions/checkout@v4` and `astral-sh/setup-uv@v5` are pinned to major versions; bump them on deprecation warnings.
