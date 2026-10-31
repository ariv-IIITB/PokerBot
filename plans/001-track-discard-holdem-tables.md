# Plan 001: Track the Discard Hold'em tables in git so every clone can package the bot

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 39ca8f8..HEAD -- .gitignore docs/STATUS.md docs/PHASE_F_V2_PROMPT.md data/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `39ca8f8`, 2026-10-31

## Why this matters

The submitted bot embeds precomputed preflop/discard tables in `bot/embedded.py`. They are
generated from `data/discard_holdem/` (6 small `.npy`/`.json` files, ~135 KB in total), but
`data/` is gitignored. Every fresh clone therefore lacks them. Implementation sessions work from
GitHub clones (see `CLAUDE.md`, "Lessons": "Implementing sessions work from GitHub"). In such a
clone the package builder (`tools/package_submission.py`) refuses to build, one test fails
(`tests/test_day1.py::test_zip_has_bot_py_at_the_top_is_small_and_reproducible`), and getting the
tables back costs a ~6-minute rebuild. Upload #2 shipped *without* its tables for exactly this
reason. Committing the ~135 KB folder removes the failure mode.

## Current state

- `.gitignore` — line 10 ignores all `*.npy`, line 11 re-includes `variant/data/*.npy` (a
  precedent for committing small tables), line 22 ignores all of `data/`:
  ```
  8  # Lab outputs and caches
  9  results/
  10 *.npy
  11 !variant/data/*.npy
  ...
  21 # Generated tables / strategies (lab/precompute.py, lab/cfr/train.py)
  22 data/
  ```
- `data/discard_holdem/` — produced by `lab/precompute.py`. Expected files (sizes in bytes,
  from `meta.json`): `classes.npy` 88528, `eq_random.npy` 14168, `eq_range.npy` 14168,
  `class_counts.npy` 7148, `class_reps.npy` 10658, plus `meta.json` (~435 bytes, contains
  `"spec_hash": "67430f7ec9d87823"`, `"samples": 6000`, `"range_top": 0.3`, `"seed": 0`).
- `bot/embedded.py` (generated, committed) records a sha of each table file under `SOURCES`,
  with keys like `"data/discard_holdem/classes.npy"`. The rebuild is deterministic: at
  `39ca8f8` a fresh `lab.precompute` run produced files whose hashes match `SOURCES` exactly.
- `tools/embed_data.py:70-93` (`_tables`) reads `data/<spec.name>/meta.json` and the `.npy`
  files; it returns no tables if the folder is missing. Do **not** modify this file.
- Docs that tell readers `data/` is gitignored and must be rebuilt:
  - `docs/STATUS.md:68-69`:
    ```
    Do not run `tools.embed_data` or the package builder without `data/discard_holdem/` (gitignored; rebuild with
    `lab.precompute --variant discard_holdem --samples 6000 --range-top 0.3`).
    ```
  - `docs/PHASE_F_V2_PROMPT.md:145`:
    ```
    - Do not run `python -m tools.embed_data` unless `data/discard_holdem/` exists (it is gitignored);
    ```
  Read the line right after line 145 too, since the sentence may continue there.
- Other docs (`docs/PHASE_E_HANDOFF.md`, `docs/PHASE_E_DONE_HANDOFF.md`,
  `docs/reports/TIER2_VS_TIER1.md`) also say "gitignored". They are historical reports: leave
  them unchanged.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Set up the venv (only if `.venv/` is missing) | `uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt` | exit 0 |
| Rebuild the tables (only if missing) | `.venv/bin/python -m lab.precompute --variant discard_holdem --samples 6000 --range-top 0.3` | last line starts `done in`, ~6 min |
| Fast test suite | `.venv/bin/python -m pytest -n auto -q` | `1103 passed, 2 skipped` (at `39ca8f8`; more if later commits added tests), 0 failed |
| Ignore check | `git check-ignore -v <path>` | exit 1 = NOT ignored, exit 0 = ignored |

## Scope

**In scope** (the only files you should modify or add):
- `.gitignore`
- `data/discard_holdem/*` (add the 6 existing files to git, unchanged)
- `docs/STATUS.md` (lines 68-69 only)
- `docs/PHASE_F_V2_PROMPT.md` (line 145, and the line after it if the sentence continues)

**Out of scope** (do NOT touch):
- `bot/embedded.py`. It is already correct, and regenerating it is not part of this plan.
- `tools/embed_data.py`, `tools/package_submission.py`, `lab/precompute.py`.
- Any other folder under `data/` (for example `data/cfr*`, other variants). Those stay ignored.
- `lab/harness.py`, `lab/engine.py`, `lab/eval.py` and the opponent bots: the owner forbids edits there.

## Git workflow

- Work on the branch you were given; if none, create `advisor/001-track-tables`.
- One commit. Message style follows `git log`, e.g. `package builder: refuse to ship without tables only for the embedded variant`.
  Suggested: `data: track data/discard_holdem tables (135 KB) so clones can package the bot`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Make sure the tables exist and match the embedded copy

If `data/discard_holdem/meta.json` does not exist, run the rebuild command from the table above
(about 6 minutes). Then check that every table file matches the hash recorded in `bot/embedded.py`:

```bash
.venv/bin/python - <<'EOF'
import pathlib
from tools.embed_data import _sha
ns = {}
exec(compile(pathlib.Path("bot/embedded.py").read_text(), "embedded", "exec"), ns)
bad = [k for k, v in ns["SOURCES"].items()
       if k.startswith("data/") and _sha(pathlib.Path(k).read_bytes()) != v]
print("MISMATCH:", bad) if bad else print("all table hashes match")
EOF
```

**Verify**: the output is `all table hashes match`.

### Step 2: Un-ignore only `data/discard_holdem/`

In `.gitignore`, replace line 22 (`data/`) with these three lines, keeping the comment on line 21:

```
data/*
!data/discard_holdem/
!data/discard_holdem/*.npy
```

Why three lines: git cannot re-include a file inside an ignored *directory*, so `data/` becomes
`data/*` (ignore the children), the second line re-includes the one folder, and the third undoes
the global `*.npy` rule from line 10 for that folder (a later rule wins).

**Verify** (each line is one command):
- `git check-ignore -v data/discard_holdem/classes.npy; echo "exit $?"` → `exit 1`
- `git check-ignore -v data/discard_holdem/meta.json; echo "exit $?"` → `exit 1`
- `git check-ignore -q data/some_other_variant/x.npy; echo "exit $?"` → `exit 0`
- `git check-ignore -q results/x.npy; echo "exit $?"` → `exit 0`

### Step 3: Add the files

`git add .gitignore data/discard_holdem`

**Verify**: `git diff --cached --name-only` lists exactly `.gitignore` and these 6 files:
`data/discard_holdem/class_counts.npy`, `class_reps.npy`, `classes.npy`, `eq_random.npy`,
`eq_range.npy`, `meta.json`. Any other path → STOP.

### Step 4: Update the two docs

- `docs/STATUS.md:68-69`: replace the sentence with
  `` `data/discard_holdem/` is committed (135 KB). If you change the variant or the precompute settings, rebuild it with `lab.precompute --variant discard_holdem --samples 6000 --range-top 0.3`, then run `tools.embed_data`, and commit both. ``
- `docs/PHASE_F_V2_PROMPT.md:145`: replace "(it is gitignored)" with "(it is committed; rebuild it only if the tables change)". Keep the rest of the bullet as it is.

**Verify**: `grep -n "gitignored" docs/STATUS.md docs/PHASE_F_V2_PROMPT.md` → no output.

### Step 5: Full suite, commit, and check in a fresh clone

1. `.venv/bin/python -m pytest -n auto -q` → 0 failed.
2. `git add docs/STATUS.md docs/PHASE_F_V2_PROMPT.md && git commit -m "<message from Git workflow>"`
3. Fresh-clone check (proves a clone now has the tables):
   ```bash
   D=$(mktemp -d) && git clone -q . "$D/clone" && ls "$D/clone/data/discard_holdem" && (cd "$D/clone" && "$OLDPWD/.venv/bin/python" -m pytest -q tests/test_day1.py tests/test_embed.py); rm -rf "$D"
   ```

**Verify**: `ls` prints the 6 file names, and pytest prints `passed` with 0 failed.

## Test plan

No new test: the existing `tests/test_day1.py::test_zip_has_bot_py_at_the_top_is_small_and_reproducible`
fails in a clone without tables, so the fresh-clone run in Step 5 is the regression check.
`tests/test_embed.py::test_committed_embedded_file_is_current` must still pass, which confirms the
committed tables match `bot/embedded.py`.

## Done criteria

- [ ] `git ls-files data/discard_holdem | wc -l` → `6`
- [ ] `git ls-files data | grep -v '^data/discard_holdem/'` → no output
- [ ] `.venv/bin/python -m pytest -n auto -q` → 0 failed
- [ ] The Step 5 fresh-clone command shows the 6 files and the tests passing
- [ ] `grep -n "gitignored" docs/STATUS.md docs/PHASE_F_V2_PROMPT.md` → no output
- [ ] `git status --short` is empty after the commit
- [ ] `plans/README.md` row 001 updated

## STOP conditions

Stop and report back (do not improvise) if:

- Step 1 prints `MISMATCH`, even after a rebuild. The tables would then differ from what the
  shipped bot embeds, and the owner must decide which copy is right.
- `.gitignore` line 22 is not `data/`, or lines 10-11 differ from the excerpt.
- `data/discard_holdem/` holds files other than the 6 listed (for example checkpoint files):
  report the names instead of adding them.
- The folder is much larger than ~135 KB (`du -sh data/discard_holdem` over 1 MB).
- Any test fails that passed before your change.

## Maintenance notes

- Whenever `variant/active.json`, the precompute settings or `lab/precompute.py` change, the
  tables must be rebuilt, re-embedded (`python -m tools.embed_data`) and committed *together*.
  `tests/test_embed.py` catches an embedded file that no longer matches its source data.
- If the variant changes after the 1 Nov Problem Statement, add the new `data/<variant>/` with
  the same three-line pattern, and remove the old folder once it is no longer used.
- `tools/embed_data.py:145` says "data/ is not committed" in a docstring. It is still true for
  other variants; reword it if this area is touched again (deliberately left out of this plan).
- Plan 002 (CI) depends on this: CI can only run the packaging tests if the tables are in the clone.
