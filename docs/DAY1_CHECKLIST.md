# Reveal day checklist (3 days)

Two people: **A** = rules & spec, **B** = protocol & infrastructure. All commands from the repo
root. Keep a log of decisions in `docs/DAY1_LOG.md` as you go.

## Day 1

### Hour 0–1 · Read, interview, spec (A) / Engine recon (B)
- **A**: read the official rules twice. Fill in `docs/VARIANT_INTERVIEW.md` question by question.
  Start from the closest preset:
  ```bash
  ls variant/catalog/
  .venv/bin/python -m lab.new_variant --from <closest_preset> --force
  $EDITOR variant/active.json
  .venv/bin/python -m lab.new_variant            # validate + explain + 2,000-hand smoke fuzz
  ```
  Read the printed plain-English hand program **next to the official rules**, line by line.
  List every red flag (needs a new plugin) and every question for the organisers.
- **B**: get the real engine running locally if provided. Capture full hands of traffic (both
  directions) into `docs/protocol_samples/`. Note the time bank rules and the launch command.

### Hour 1–3 · Protocol adapter (B) / Rule checks (A)
- **B**: follow `docs/PROTOCOL_ADAPTER_GUIDE.md`:
  ```bash
  cp bot/protocols/terse.py bot/protocols/<engine>.py        # or jsonl.py
  # edit, register in bot/protocols/__init__.py ADAPTERS, add MALFORMED lines in tests/helpers.py
  .venv/bin/python -m pytest tests/test_adapters.py -n auto
  POKERBOT_PROTOCOL=<engine> .venv/bin/python -m pytest -n auto
  ```
  Replay the captured traffic through `python -m bot.main --protocol <engine>` and check replies.
  If the real engine is available, play the bot against itself through it.
- **A**: hand-check 5 scenarios from the rules document against the engine
  (`tests/test_betting.py` / `tests/test_payoffs.py` show how to script a hand on a rigged deck):
  blinds and first actor, a min-raise, an all-in for less, every special action, a showdown.

### Hour 3–6 · New plugin if needed (A, B helps)
- Only for red flags. Follow `docs/WRITING_A_PLUGIN.md` (copy `bot/game/steps/_template.py`
  and `tests/test_redraw.py`). Then:
  ```bash
  .venv/bin/python -m pytest -n auto && .venv/bin/python -m pytest -m slow -n auto
  .venv/bin/python -m lab.new_variant
  ```

### Hour 6–7 · First submission (safety net)
```bash
.venv/bin/python -m tools.package_submission --protocol <engine> --zip
```
Upload `dist/submission.zip` (Tier 2 + generic layer) even if not tuned yet. Verify on the
platform that it starts and plays.

### Overnight · Precompute
```bash
.venv/bin/python -m lab.precompute --variant variant/active.json --hours 8 --samples 20000
```
Resumable: rerun the same command to continue. Check `data/<variant>/meta.json` in the morning.

## Day 2 · Tune

- Baselines on the real variant (expect Tier 2 to beat every sparring bot and Tier 1):
  ```bash
  .venv/bin/python -m lab.harness tier2 tier1 random_legal calling_station tight maniac \
      --variant variant/active.json --seeds 16 --hands 400
  ```
- Freeze a snapshot before tuning: `.venv/bin/python -m lab.versions create day2_base`
- Sweep the parameters that matter most (equity thresholds, bluffing, sizing, inference):
  ```bash
  cp lab/spaces/tier2_example.json lab/spaces/day2.json      # edit ranges
  .venv/bin/python -m lab.sweep tier2 lab/spaces/day2.json --mode random --n 16 \
      --opponents tier1 maniac tight calling_station --seeds 8 --hands 200
  ```
  Copy winning values into `bot/config/tier2.json` only when they beat the baseline by more
  than 2 standard errors; re-check against the `day2_base` snapshot:
  `.venv/bin/python -m lab.harness ...` with `lab.versions.snapshot_player("day2_base")`.
- Timing on the real variant (must stay well under the bank at ×2):
  ```bash
  .venv/bin/python -m lab.timing_bench --variant variant/active.json --hands 1000
  .venv/bin/python -m lab.memory_check --variant variant/active.json
  .venv/bin/python -m lab.fuzz --hands 100000
  ```
- Upload an improved package at the end of the day.

## Day 3 · Freeze, package, upload, verify

- Morning: last sweep only if Day 2 found a clear direction. No new features after noon.
- Full suite, then the package with all its checks:
  ```bash
  .venv/bin/python -m pytest -n auto && .venv/bin/python -m pytest -m slow -n auto
  .venv/bin/python -m tools.package_submission --protocol <engine> --zip
  ```
- Upload, then verify on the platform: it starts, plays a full match, no timeouts, no
  illegal-action warnings. Keep the previous zip ready to re-upload.
- Tag the release: `git tag submitted-final && .venv/bin/python -m lab.versions create final`
