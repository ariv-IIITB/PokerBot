# INT1 report: `cands/final_disc.py` (final + DISC1 `disc_eq=on`, normal build) — safety verdict, not strength

Build: `panav-bots/loop/cands/final_disc.py` (718,260 B; base `final/bot.py` untouched, 715,908 B). Made with `bundle_tool.py unpack final/bot.py` ->
policy module from the DISC1 build (`final_disc_seeded.py`) + `"disc_eq": "on"` in config -> `pack`. Tools I added: `tools/int1_check.py`
(per-reply timing / illegal / forfeit / RSS harness, real `pokerbots` protocol), `tools/int1_scan.py` (static scan). Raw output: `results/int1/`.
No `holdout/*` bot was read or run. Spar bots used (`eqtag`, `potctl`) are B1/B2 dev bots.

## MATCH RESULTS FIRST (check 7). cand = final_disc, 6 duplicate pairs x 200 hands each (seeds 100-105, real protocol, non-seeded builds)
| opponent | wins W/N (pair-avg of two legs; ties .5) | chips/hand ± SE | crash/forfeit |
|---|---|---|---|
| final (non-seeded) | 1.5 / 6 (score 0.250) | -0.04 ± 0.73 | none |
| lakshya1 | 3.0 / 6 (0.500) | -0.11 ± 0.60 | none |
| spar/eqtag | 2.5 / 6 (0.417) | -0.16 ± 0.67 | none |
| spar/potctl | 1.0 / 6 (0.167) | -0.49 ± 0.48 | none |
Pooled 8.0 / 24 wins, mean about -0.20 chips/hand. N is tiny (SE is 0.5-0.7 chips/hand, the DISC1 effect is +0.075), so none of this says
anything about strength; the point of this check is only "no crash, no forfeit, no illegal reply": met in all 4 x 12 legs. The 1.5/6 vs
final is within noise (-0.04 ± 0.73 chips/hand).

## 1. Diff of unpacked sources vs final: only DISC1 + the CONFIG flag — PASS
`diff -r` of the two unpacks: `config.json` gains `"disc_eq": "on"` (nothing else; no `sample_seed`/`force_mode`/`solver_passes`/`slowdown`),
and ONLY `botsrc.policy.py` differs: import `from shared import evaluator as EVAL`, constants `DISC_DELTA=0.12`, `DISC_M=1000`, `s1_slots` in the
discard cache, the `disc_eq` branch in the discard decision, and the new `disc_equity_pick` method. The other 24 modules are identical; the
text before `_SOURCES` differs only on the `CONFIG = {...}` line; the text after `_SOURCES` is byte-identical (checked in Python). Shipped:
`CONFIG = {'river_allin_rule': 'mix', 'preflop_allin_rule': 'on', 'small_bet': 'gated', 'river_solver': 's1', 'solver_fold': 'on', 'river_min_ms': 25.0, 'exploit': 'station,prefold,riverbluff,rivernarrow', 'disc_eq': 'on'}`.
Full diff: see the command output in the session; it is exactly `policy.py +46 lines` as listed above.

## 2. Legality fuzz — PASS (illegal 0, forfeits 0)
Cand vs engine-side misbehaving opponents (`lab.fuzz.WeirdPlayer`: random sizes, min-raise spam, all-in spam, malformed replies, mixed) and the
organisers' starter bot; 2 seeds x 2 seats = 4 legs of 200 hands each, once with init `total_hands=400` (bank 60 s) and once with
`total_hands=1000` (bank 150 s):

| opponent | init total_hands | legs (200h) | decisions | illegal | forfeits | worst reply ms | peak RSS MB |
|---|---|---|---|---|---|---|---|
| weird:mixed | 400 | 4 | 1451 | 0 | 0 | 279 | 100 |
| weird:random_size | 400 | 4 | 1138 | 0 | 0 | 378 | 100 |
| weird:all_in | 400 | 4 | 1469 | 0 | 0 | 328 | 89 |
| weird:min_raise | 400 | 4 | 4627 | 0 | 0 | 327 | 122 |
| weird:malformed | 400 | 4 | 926 | 0 | 0 | 275 | 98 |
| starter_bot.py | 400 | 4 | 3954 | 0 | 0 | 335 | 124 |
| weird:mixed | 1000 | 4 | 1441 | 0 | 0 | 357 | 95 |
| weird:random_size | 1000 | 4 | 1304 | 0 | 0 | 301 | 100 |
| weird:all_in | 1000 | 4 | 1471 | 0 | 0 | 360 | 85 |
| weird:min_raise | 1000 | 4 | 4611 | 0 | 0 | 325 | 119 |
| weird:malformed | 1000 | 4 | 931 | 0 | 0 | 357 | 92 |
| starter_bot.py | 1000 | 4 | 3957 | 0 | 0 | 309 | 123 |

## 3. Reply time under the slowdown emulation (final vs cand, same harness) — PASS as a non-regression; see caveat
Both bots are `*_sd2` copies (`slowdown: 2.0` added; EVAL-ONLY, these copies are not shipped) so the bot's calibration/time-manager see a 2x slower
machine; opponent lakshya1; per-reply wall time measured by the harness. Hard limit 1.5 s.

| bot | init | legs x hands | decisions | mean ms | p99 ms | max ms | bank used max / mean (s) | % of bank (max) | illegal | forfeit |
|---|---|---|---|---|---|---|---|---|---|---|
| final (200h legs) | 400 | 6 x 200 | 4133 | 25.6 | 131 | 451 | 19.1 / 17.6 of 60 | 32% | 0 | 0 |
| final (200h legs) | 1000 | 6 x 200 | 4220 | 24.9 | 127 | 463 | 19.5 / 17.5 of 150 | 13% | 0 | 0 |
| cand (200h legs) | 400 | 6 x 200 | 4093 | 25.8 | 132 | 487 | 18.8 / 17.6 of 60 | 31% | 0 | 0 |
| cand (200h legs) | 1000 | 6 x 200 | 4072 | 25.7 | 129 | 423 | 18.9 / 17.5 of 150 | 13% | 0 | 0 |
| final (FULL-length legs) | 400 | 4 x 400 | 5083 | 24.6 | 131 | 426 | 34.4 / 31.3 of 60 | 57% | 0 | 0 |
| final (FULL-length legs) | 1000 | 2 x 1000 | 6332 | 24.8 | 132 | 687 | 80.3 / 78.6 of 150 | 54% | 0 | 0 |
| cand (FULL-length legs) | 400 | 4 x 400 | 5064 | 25.0 | 131 | 401 | 33.2 / 31.6 of 60 | 55% | 0 | 0 |
| cand (FULL-length legs) | 1000 | 2 x 1000 | 6356 | 25.6 | 132 | 371 | 85.4 / 81.4 of 150 | 57% | 0 | 0 |

Per-reply: cand mean 25.0-25.8 ms vs final 24.6-25.6 ms (+0.2..+0.8 ms, about the 1.6 ms discard MC spread over ~3 decisions/hand), p99 129-132
vs 127-132 ms, worst 371-487 ms vs 426-687 ms: well under 1.5 s, and the worst replies are the river solver / first decision, not the discard.
Total bank use of cand vs final: 55% vs 57% (Stage 1) and 57% vs 54% (Stage 2) of the bank, run-to-run noise of the wall-clock solver is of that size.
**Caveat (honest):** under this emulation BOTH final and cand use more than 50% of the bank in the full-length legs (54-57%), so the
absolute "<= 50% projected at 2x" bar from CLAUDE.md is not met by the base either; DISC1 does not change it (difference is within noise)
and the pacing keeps both well below exhaustion (no forfeit, worst leg 85.4 s of 150 s). I did not tune the time manager (out of scope).
`lab.timing_bench` itself was run first against the starter bot and is not informative (starter folds almost everything: mean 0.14 ms).

## 4. Memory — PASS
Peak RSS of the bot process over every leg above (`RUSAGE_CHILDREN`): 85-124 MB (fuzz), 116-123 MB (full-length 400/1000 hands); limit 1024 MB.

## 5. Sandbox — PASS
`results/int1/scan.txt` (`tools/int1_scan.py`, AST over all 25 embedded modules + loader): imports = stdlib + numpy + the bot's own packages only, identical
import set to final; no `socket/subprocess/multiprocessing/threading/ctypes/urllib/pathlib/shutil/scipy`; no `open/load/fromfile/read_text/Popen/system`
calls (the only flagged names are the two `.run` methods of the river solver, unchanged vs final). Runtime audit hook (`sys.addaudithook` around a real
60-hand x 2 legs run via runpy): events = `ctypes.dlopen(None)` from numpy's import, and the wrapper's own read of the script; no
socket, subprocess, exec, fork, file write or other file open.

## 6. Size — PASS
`final_disc.py` = 718,260 bytes (0.72 MB; final 715,908), limit 5 MB.

## 7. Matches — PASS (no crash, no forfeit, no illegal reply; results at the top)

Checks 1-7: 1 PASS, 2 PASS, 3 PASS (relative to final; the absolute 50% bar is exceeded by final too, see caveat), 4 PASS, 5 PASS, 6 PASS, 7 PASS.
PASS
