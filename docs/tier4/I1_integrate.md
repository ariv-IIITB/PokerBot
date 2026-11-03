# I1: integrate and decide what ships (Opus, Sun 9–Mon 10)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, the final handoffs `PD.md`, `DC.md`, `RC.md` (and `RA.md` if R
stopped at the spike). Don't read the other sub-plans unless a handoff leaves a question open.
Branch `tier4/main` from `origin/tier4/base`. Seeds 40000+. Use the whole machine (no other sessions should run evals now).

## Tasks
1. **Merge** `origin/tier4/p`, `origin/tier4/d`, `origin/tier4/r` into `tier4/main`. Expected conflicts: `bot/embedded.py`
   (regenerate with `tools.embed_data`, never hand-merge), `bot/main.py` (registry lines: keep all). Anything else:
   stop and say so in the handoff.
2. **Candidates:** the incumbent (from PA: `tier3x` or `tier3`) with D's and R's KEEPs, and, if gate P passed,
   `tier4p` (its members inherit D's and R's changes through Tier 3).
3. **Combined gates** (the pieces were tested alone; now together):
   - combined timing at 2× slower, 400/60 s and 1000/150 s, vs calling_station and trapper: ≤ 50 % of the bank;
     deadline hits ≤ baseline + 2√baseline; `lab.memory_check` < 500 MB;
   - best candidate vs the incumbent as shipped today (`tier3` on `main`): head-to-head 100 pairs, score ≥ 0.5 + 2 SE
     to call it an improvement; training pool two-part KEEP; a Stage 2 run (1000 hands, 30 pairs).
4. **Held-out, once:** two `--final` runs on the held-out pool (incumbent and the chosen candidate, same seeds). If the
   candidate is below the incumbent by > 2 SE on the sum, the incumbent ships.
5. **Package:** `tools.package_submission --zip --stage2 --brain <chosen>`; record the sha256 in `docs/SUBMISSIONS.md`.
   Don't upload: the user does.
6. Update `docs/STATUS.md` (Tier 4 row, what shipped, what was dropped and why). Fast suite and slow timing green. Push
   `tier4/main`, and ask the user before merging it into `main`.

## Done when
- `docs/tier4/handoff/I1.md`: which brain ships and why, every combined number with ± SE, the held-out result, the
  package hash. That note is the input for Tier 5 (merging the teammate's CFR).
