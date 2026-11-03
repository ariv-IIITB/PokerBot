# S0: recordings and the match-score script (Sonnet, cloud)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file. Branch `tier4/s0` from `origin/tier4/base`.
Files you may edit: `lab/opps/record.py`, `lab/opps/score_compare.py` (new), `logs/records/`, tests for them.

Other sessions need two things from you: **recordings on fresh seeds that include the opponent's dealt cards on
every hand** (DB, PD, RC), and **a script that compares match scores** (the second half of every two-part KEEP).

## Tasks

1. **Recorder.** `lab/opps/record.py` stores per hand `hole3` (ours), `opp` (the opponent's cards *only at showdown*)
   and the actions. Add `opp_hole3`: the opponent's 3 dealt cards on **every** hand, and their discard when one
   happened. The lab engine knows all cards, so this is lab-side only. Keep the old fields unchanged (X0 tools read
   them). Add a round-trip test (record → load → `opp_hole3` present on fold hands too).
2. **Recordings.** Run with Tier 3 (default brain), locks off, seeds 9000–9011, `--processes` per README rule 3 (N below):
   ```bash
   .venv/bin/python -m lab.opps.record --brain tier3 --pool train,starter,calling_station,tight,maniac,random_legal,all_in --pairs 12 --first-seed 9000 --processes N --out logs/records/s0_9000
   ```
   Check the size. If it is over ~20 MB, gzip the files and make the loader read `.gz`. Commit them, so other sessions
   (and other machines) can use them. Never record held-out bots.
3. **Score script** `lab/opps/score_compare.py BEFORE.txt AFTER.txt`: read two `lab.eval` result files (the locks-on
   runs), and print per bot and overall the mean match score for each, the difference, its SE over pairs, and
   `KEEP-score` / `DROP-score` (DROP if the overall mean is lower by > 2 SE). Look at `lab/eval.py`'s `--compare` and
   its output format first, and reuse its parsing rather than writing a new parser. Test it on two files in
   `logs/g/recheck/` (e.g. `pool_t2.txt` vs `pool_t3.txt`, if present) and in a unit test.
4. Fast suite green, push, handoff.

## Done when
- `logs/records/s0_9000/` is committed with `opp_hole3` on every hand, for the 6 training + 6 sparring bots.
- `score_compare.py` runs on real files and has a test.
- `docs/tier4/handoff/S0.md` says where the recordings are, the file format (fields), the size, and the script's usage.
