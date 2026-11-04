# I1: integrate and decide what ships (Opus, cloud, last)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, the final handoffs `PD.md`, `DC.md`, `RC.md` (and `RA.md` if R
stopped at the spike). Don't read the other sub-plans unless a handoff leaves a question open.
Branch `tier4/main` from `origin/tier4/base`. Seeds 40000+. `--processes` per README rule 3.

**What ships by default:** `tier3` as packaged in upload candidate #5, unless a candidate passes every gate below.
Level within noise means `tier3` ships.

## Tasks
1. **Merge** `origin/tier4/p`, `origin/tier4/d`, `origin/tier4/r` into `tier4/main`. Expected conflicts: `bot/embedded.py`
   (regenerate with `tools.embed_data`, never hand-merge), `bot/main.py` (registry lines: keep all). Anything else:
   stop and say so in the handoff.
2. **Candidates:** the incumbent (from PA: `tier3x` or `tier3`) with D's and R's KEEPs, and, if gate P passed,
   `tier4p` (its members inherit D's and R's changes through Tier 3).
3. **Combined gates** (the pieces were tested alone; now together):
   - combined timing, 400/60 s and 1000/150 s, vs calling_station and trapper: README rule 3's ratio (≤ 1.4 × Tier 3);
     deadline hits ≤ baseline + 2√baseline; `lab.memory_check` < 500 MB with the river solver on (the old 43 MB figure was Tier 3 without it); `lab.fuzz --subprocess --hands 2000` on the final package;
   - **Stacking order test (user, 2026-11-04):** before the head-to-head, add the KEEPs one at a time on top of the
     incumbent (order: DA, PB/PD portfolio, O3 river narrowing, DC discard, RD/RC river solver if it was kept), each step
     a 30-pair training-pool run (locks off, same seeds, back to back), and record the sum of chips/hand after each step.
     A piece that lowers the running sum by > 1 SE is dropped or re-tuned in the stack (pieces were only tested alone);
     the candidate is the best stack, not "everything kept".
   - best candidate vs the incumbent as currently shipped (`tier3` on `main`): head-to-head 100 pairs, score ≥ 0.5 + 2 SE
     to call it an improvement; training pool two-part KEEP; a Stage 2 run (1000 hands, 30 pairs, then sequential). All comparisons use the README's sequential test.
   **Retries, at most 2.** Retry 1 drops the piece the failing gate points at (if unclear, the next in slip order:
   R's restricted p → DC → DB's learned rule → R entirely → `tier4p`'s portfolio), and re-runs only the failing gate.
   Retry 2 falls back to the incumbent (`tier3x` or `tier3`) plus the KEEPs that survived. If that fails too, `tier3`
   (#5) ships.
4. **Held-out, once:** two `--final` runs on the held-out pool (the final pick and the incumbent, same seeds), only after
   the combined gates have picked the candidate, never before a retry. If the candidate is below the incumbent by
   > 2 SE on the sum, the incumbent ships.
5. **Package:** `tools.package_submission --zip --stage2 --brain <chosen>`; record the sha256 in `docs/SUBMISSIONS.md`.
   Don't upload: the user does. Optional, if the user can: one `tests/test_timing_slow.py` run of the final package on
   the user's laptop (the machine the 2× rule was calibrated on) before upload.
6. Update `docs/STATUS.md` (Tier 4 row, what shipped, what was dropped and why). Fast suite and slow timing green. Push
   `tier4/main`, and ask the user before merging it into `main`.

## Done when
- `docs/tier4/handoff/I1.md`: which brain ships and why, every combined number with ± SE, the held-out result, the
  package hash. That note is the input for Tier 5 (merging the teammate's CFR).
