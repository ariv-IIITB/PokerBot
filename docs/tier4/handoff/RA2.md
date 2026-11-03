# RA2 handoff: river solver as close to exact as the box allows

**Result: exploitability roughly halved at every box; the ≤ 0.3 % target at 10 ms is NOT reached** (0.98 %); 0.3 % needs
~800 passes ≈ a 40 ms box. Code commit `f862ca9`, branch `tier4/ra2` (cut from `tier4/r` `e9e1bea`). Full tables:
`docs/reports/TIER4_RIVER.md` (RA2 section); raw logs in the notes folder `ra2_logs/`.
Machine: Intel Core Ultra 5 225H, `nproc` 14 (shared, every timing run under the laptop lock, 1 BLAS thread), Python 3.11.
Files changed: `bot/strategy/river_solver.py`, `lab/river_bench.py`, `tests/test_river_solver.py`, the report only.

## Box-size curve (60 pinned spots, same run back to back; exact full game, pot = 1, mean ± SE, median in brackets)
| box (this laptop) | RA: 64 equal-mass, f32 | **final `auto=True`** | buckets |
|---|---|---|---|
| 10 ms (= 20 ms on the 2× slower server) | 154 passes, 0.0177 ± 0.0053 (0.0108) | **144, 0.0098 ± 0.0010 (0.0082)** | 48 |
| 20 ms | 402, 0.0091 ± 0.0008 (0.0085) | **326, 0.0057 ± 0.0006 (0.0046)** | 64 |
| 40 ms | 892, 0.0079 ± 0.0007 (0.0068) | **730, 0.0038 ± 0.0005 (0.0028)** | 64 |
| 80 ms | 1888, 0.0076 ± 0.0007 (0.0065) | **1114, 0.0030 ± 0.0004 (0.0019)** | 96 |
**Full ranges (990/903 combos), medians: their range 2.5 ms (p90 3.2) + ranks 0.5 ms + setup 0.5 ms (48 buckets) / 0.6 (64) / 0.9 (96) = ~3.6 ms; no sampling needed.** Our range here is uniform (free); RB's own-range build is extra.

## Steps (kept / dropped)
1. Ranks: one evaluation per combo + last-board cache (0.63 → 0.48 ms cold, 0.06 warm). Bucket kernel without `np.add.at`
   (setup 3.0 → 0.23 ms at 64 buckets). KEPT.
2–3. **Card removal inside buckets** (pair-sharing mass from per-bucket card histograms; exact with one combo per bucket):
   bucketing floor 0.65 % → 0.30 % (64), 0.21 % (128), 0.16 % (256), 0.08 % (512). KEPT. By-value buckets: no gain, dropped.
4. Exact when affordable: `auto` drops zero-weight combos and solves exact (dense) if both fit the bucket count. KEPT (tested).
   The real ranges (903/990 live) never qualify.
5. ½ pot back: worse at every box (0.031 / 0.010 / 0.006 / 0.004 in its own game). DROPPED.
6. PCFR+, DCFR, alternating, averaging power 1–5, coarse-to-fine warm start: none beats CFR+ with t² (DCFR/alternating
   worse). DROPPED, code removed.
7. Reuse in a hand: 17 % of river decisions are second ones, already easy (0.005 vs 0.011 at 10 ms); only the ranks cache
   is reused. No regret reuse.
+ float64 in `auto`: float32 is no faster here and hits denormals on 5–8 % of spots (up to 3.4× per pass).

## For RB
* Call `solve_river(..., auto=True, cfg=TreeCfg(bet_sizes=(1.0, INF), raise_sizes=(1.0, INF)))`: it picks float64, drops
  zero-weight combos, exact if small, else card-removal buckets from the time left (`AUTO_BUCKETS`). Signature and
  `SolveResult` unchanged; new keywords `card_removal=False`, `auto=False` default to today's behaviour. `hand_ranks`
  now caches the last board: pass the same evaluator object and board for a second decision.
* The largest box the bank allows is worth taking up to ~40 ms (0.38 %); the curve is flat beyond. The first solve in a process
  is a bit slower (cold arrays): consider one dummy solve at start-up.
* Tests: `tests/test_river_solver.py` 25 passed; fast suite (`-n 4`) 1314 passed, 2 skipped; `tests/test_timing_slow.py`
  10 passed (locked). Nothing in `bot/` imports the solver yet, so Tier 3's timing is unchanged.
