# INT2 report: submission candidates (final + DISC1 [+ raw probe])

Branch `loop/int2`. Nothing in `panav-bots/final/bot.py` or `holdout/*` was touched or opened; nothing pushed to `panav-bots-12nov`.
All bots below are **normal builds** (no `sample_seed`, `force_mode`, `solver_passes`, `slowdown` in the shipped CONFIG).

## 1. MATCH WINS first (duplicate pairs = "matches"; win = pair chips > 0; real `pokerbots` protocol, non-seeded)

**A = final+DISC1+probe** (`sub_disc_probe.py`), **F = final**, **C = final+probe only** (reference, `cands/sub_probe_only.py`), **B = final+DISC1 only** (`sub_disc_only.py`).

| opponent (24 pairs x 200h, seeds 41000-41023) | F wins (ch/h) | **A wins (ch/h)** | B wins (ch/h) | C wins (ch/h) |
|---|---|---|---|---|
| lakshya1 | 8/24 (-0.45±0.32) | 16/24 (+0.53±0.25) | 9/24 (-0.31±0.29) | 17/24 (+0.73±0.37) |
| new_trapper | 12/24 (+0.38±0.31) | 6/24 (-0.97±0.30) | 11/24 (+0.02±0.31) | 7/24 (-1.04±0.35) |
| conv_opp3 | 10/24 (-0.22±0.27) | 19/24 (+0.51±0.23) | 13/24 (+0.17±0.26) | 16/24 (+0.49±0.30) |
| new_eqrandom | 18/24 (+0.30±0.30) | 14/24 (+0.45±0.30) | 13/24 (+0.04±0.30) | 13/24 (+0.06±0.37) |
| eqtag (spar) | 12/24 (+0.11±0.28) | 17/24 (+0.43±0.27) | 14/24 (+0.28±0.29) | 16/24 (+0.35±0.27) |
| potctl (spar) | 12/24 (+0.07±0.38) | 17/24 (+0.60±0.26) | 13/24 (-0.03±0.40) | 16/24 (+0.39±0.24) |
| polar (spar) | 14/24 (+0.69±0.37) | 21/24 (+1.16±0.23) | 19/24 (+1.45±0.37) | 20/24 (+1.17±0.39) |
| **POOLED 168** | 86/168 (51.2%) +0.13 | **110/168 (65.5%) +0.39** | 92/168 (54.8%) +0.23 | 105/168 (62.5%) +0.31 |

Paired over the same 24 seeds (SE over seeds): **A-F +14.3 ± 5.5 pp wins, +0.27 ± 0.14 ch/h**; **A-C (probe only) +3.0 ± 4.8 pp, +0.09 ± 0.13** (no bad interaction: A is not worse than probe-only); A-B +10.7 ± 3.8 pp, +0.16 ± 0.11; C-F +11.3 ± 4.8 pp; B-F +3.6 ± 5.1 pp.

Head-to-head (40 pairs x 200h, seeds 40000-40039): **A vs final: A MATCH WINS 17/40 (42%)**, -0.24 ± 0.23 ch/h (above the 40% flag, SE of the win rate is about 8 pp, so this is noise-level but not a positive). A vs C (24 pairs, seeds 40100+): -> 0.500 match score, +0.13 ± 0.31 ch/h.

Lakshya1, 100 fresh pairs each (seeds 40000-40099; requested by parent; normal builds):
| stage | A | final |
|---|---|---|
| S1 (200h legs) | **56/100 (56%)**, +0.25 ± 0.16 ch/h | 50/100 (50%), -0.09 ± 0.14 ch/h |
| S2 (500h legs) | **55/100 (55%)**, +0.02 ± 0.11 ch/h | not finished (stopped at 5 pairs to free CPU; for reference earlier base was 9/24) |
Progress log: `reports/int2_lakshya_progress.txt`. Note the S2 chips edge is flat (+0.02); the matches won are 55%.

Weakness (known from PROBE-VAL, not an interaction): vs `new_trapper` A 6/24 (-0.97 ch/h) and C 7/24 (-1.04) vs F 12/24, B 11/24. It comes from the probe, not DISC1.

## 2. Safety table (A = with probe; B checked quickly where stated)

| check | build | result |
|---|---|---|
| 1. Diff vs final / config | A | **PASS** (see section 4) |
| 2a. Legality fuzz (`lab.fuzz.WeirdPlayer` mixed/random_size/all_in/min_raise/malformed + starter bot; init total_hands 400 and 1000; 2 seeds x 2 seats x 200h each) | A | **PASS**: 12 rows, 0 illegal, 0 forfeits, worst reply 393 ms (`results/int2/fuzz_A.jsonl`) |
| 2a'. same, B (= `final_disc.py`) | B | PASS in INT1 (0 illegal, 0 forfeits, worst 378 ms); identical file, not re-run |
| 2b. Reply time under slowdown 2.0 emulation (EVAL-only `*_sd2` copies), full-length legs vs lakshya1 | A vs F | **PASS**: init 400 (bank 60): A worst reply 708 ms, bank used 38.6 s; F worst 450 ms, 35.6 s. init 1000 (bank 150): A worst 454 ms, 86.2 s (57%); F worst 364 ms, 85.5 s. 0 illegal, 0 forfeits, legs complete. Worst replies < 1.5 s. Bank use A vs F within about +3 s (400h) / +0.7 s (1000h). **Caveat:** measured with 3 other jobs on the 4 cores, so absolute bank use is inflated (A 64% of the 60 s bank at 400h); and the 50%-at-2x bar was already missed by the base in INT1 (54-57%). Pacing keeps both far from exhaustion. B: INT1 numbers (55-57%). |
| 3. Peak RSS | A | **PASS** 85-129 MB (<1 GB) |
| 4. Static sandbox scan (`int1_scan.py`) | A | **PASS**: imports = stdlib + numpy + own packages, identical set to final; no forbidden module; flagged calls only the two unchanged river-solver `.run` methods; nothing flagged outside `_SOURCES` |
| 5. Size | A / B | **PASS** 732,237 B / 718,260 B (< 5 MB) |
| 6. `python3.11 bot.py` starts, answers protocol init | A / B | **PASS**: starts, clean exit on EOF; with init+new_hand+action_request, first reply 0.35 s after launch (ran under CPU load). NOTE: the container's system `python3.11` has no numpy, so there the bot printed `DHBOT DEGRADED: numpy is NOT available` and plays fallback actions (the designed safety path); all real runs used the venv python 3.11 with numpy. |
| 7. 60-hand real-protocol match vs starter bot (single `bot.py` in its own dir) | A / B | **PASS**: no crash/forfeit; A +21.1 ch/h, B +16.7 ch/h, match score 1.0 |
| 8. Total forfeits in all strength duels | A | **PASS** 0 |

## 3. Recommendation

**Ship A (`bot_with_probe.py`)** if you accept the trapper-type risk: pooled match wins 65.5% vs final 51.2% (+14.3 ± 5.5 pp, about 2.6 SE) and vs B 54.8% (+10.7 ± 3.8 pp), with no sign of a bad DISC1 x probe interaction (A vs probe-only +3.0 ± 4.8 pp; A is not worse on any decision rule: h2h vs final 42% > 40%; pooled wins above base). Lakshya1 (the stated target): A 56/100 and 55/100 vs final 50/100 (S1). The DISC1-only build B adds little alone (+3.6 ± 5.1 pp over final) and carries none of the trapper risk: **ship B (`bot_without_probe.py`) instead** if trapper-style opponents (play that is passive then big) are expected to be a meaningful share of the field, because A drops about 1 ch/h and about 6 of 24 matches vs `new_trapper`/`trapper`-type bots. Do NOT ship plain final: it is the weakest on this pool. The h2h A vs final at 42% (17/40) is a mild flag, not a stop.

## 4. Diff vs `panav-bots/final/bot.py` (unpack with `bundle_tool.py`)

A (`cands/sub_disc_probe.py`, built from `loop/meta1 builds/sw_probe.py` modules + DISC1 policy):
- `CONFIG`: `{'river_allin_rule': 'mix', 'preflop_allin_rule': 'on', 'small_bet': 'gated', 'river_solver': 's1', 'solver_fold': 'on', 'river_min_ms': 25.0, 'exploit': 'station,prefold,riverbluff,rivernarrow,probe', 'disc_eq': 'on', 'force': 'probe'}` (no sample_seed/force_mode/solver_passes/slowdown; `force: probe` = raw ungated probe as in PROBE-VAL; `foldall`, `valuebet`, `potfold` are not in `exploit`/config, so they are OFF).
- Modules changed: `botsrc.exploit.py` (probe switch code, = sw_probe), `botsrc.main.py` (potfold wiring, inert because `potfold` is absent from config; = sw_probe), `botsrc.policy.py` (DISC1 `disc_eq` change from `final_disc.py` + the two `pf_proxy` cache lines from sw_probe, merged by `patch` with no conflict; 43 differing lines vs final), new module `botsrc.potfold.py` (inert). All other modules byte-identical to final (checked with `diff -rq` of unpacks). Caveat: the sw_probe source carries the dormant code of the other switches; it is not reachable with this config.
- B = `cands/final_disc.py` copied unchanged (only `policy.py` +46 lines and `"disc_eq": "on"`).

## 5. Deliverables and sha256

| file | bytes | sha256 |
|---|---|---|
| `panav-bots/submission/bot_with_probe.py` (A) | 732,237 | `2309eedc310d33cb408374ac591da2e00357a85d0bf41ddb40ae0febb4362afe` |
| `panav-bots/submission/bot_without_probe.py` (B) | 718,260 | `170a6a274c4d3789c945a7866fbfd59d6ed2db4796a946525590c53122b38ff7` |
| (reference) `panav-bots/final/bot.py` | 715,908 | `84f61b05dd455e21ec63dcae699aa6555aaf0adbb89e9242c2b65365e622473b` |

Reproduce: `.venv` (py3.11 + numpy); scripts in `panav-bots/loop/int2/` (`run.py` queue, `prog.py`/`lak.sh` lakshya runs, `fuzz.sh`, `timing.sh`, `summ.py`); raw results in `panav-bots/loop/results/int2/`.
Not done: S2 (500h) final baseline on lakshya1; lakshya1 500h x 24 pairs on a separate seed block (S2 100 pairs on A covers it).
