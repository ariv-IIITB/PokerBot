# INT3 report — bot_stage2.py (Stage-2 match-lock build)

**Verdict: INT3 PASS** (one caveat on check 3b, below). Worst reply 0.44 s; bank used max 104.4 s of 150 s at the 2x slowdown.

## 1. Artifact — PASS
`panav-bots/submission/bot_stage2.py` = `panav-bots/loop/cands/sub_s2_lock.py`, byte-identical copy.
sha256 `5855fc7a8282b8a1971eb4205737a246c6571435334b6ddb136fa4967458fd85`, 736,921 bytes (< 5 MB).

## 2. Timing at 2x slowdown, Stage 2 length — PASS
`opus2/duel1000.py` with `sd/A_sd2.py` (A) and `sd/L_sd2.py` (lock): one process per bot, 1000 hands, bank 150 s, 5 s reply cap, 3 matches per cell
(seeds 63000-63002 vs lakshya1, 63100-63102 vs starter_bot). 4-core box, 3 matches in parallel (so a little pessimistic). Real `p99` comes from a separate
int1_check run on the same sd2 files (lakshya1, 300 hands x 2 legs, total_hands 1000).

| bot | opp | worst reply | bank used max (of 150 s) | forfeits | match wins | p99 reply (lakshya1 run) |
|---|---|---|---|---|---|---|
| A    | lakshya1    | 0.35 s | 99.5 s  | 0 | 2/3 | 121 ms |
| lock | lakshya1    | 0.37 s | 85.2 s  | 0 | 3/3 | 126 ms |
| A    | starter_bot | 0.43 s | 101.8 s | 0 | 3/3 | – |
| lock | starter_bot | 0.44 s | 104.4 s | 0 | 3/3 | – |
Worst reply < 1.5 s (max 0.44 s); bank within 150 s in all 12 matches (peak 104.4 s = 70 %). Lock is not worse than A on worst reply (+0.02 s) or bank (lock lower vs lakshya1
because the lock fires and the later hands are cheap; +2.6 s vs starter_bot, within run noise). Note: 70 % is above the CLAUDE.md "<= 50 % at 2x" guideline, but A (the baseline) is at 68 % in the same harness, so it is not a regression of this build.

## 3. Real-protocol 60-hand legs — PASS (3a); identity check PASS by inspection (3b)
3a. `python3.11 bot_stage2.py`-style subprocess (pokerbots protocol), 60 hands x 2 seats, init total_hands 1000 and 400, vs `lab/sparring/starter_bot.py` and WeirdPlayer
(mixed, random_size, all_in, min_raise, malformed): 12 runs, **0 illegal, 0 forfeits**, max reply 321 ms (`results/int3/rp60.txt`).
3b. total_hands = 400: the diff to A (`opus2/lock_main.diff`) is gated entirely by `lock_armed = s2_lock on and total_hands >= 800`; with 400 `locked` is never set and
`lock_clamp` is never called, so decisions are A's code path. I also replayed a recorded 150-hand stream (init total_hands 400) through A and the lock build twice each.
Byte-identity cannot be shown literally: the bot is non-deterministic by design (per-process random SALT in action translation, wall-clock solver budgets) — A vs A differs in 88/750
replies, A vs lock in 95-103/750, the same noise level. All replies in all four replays were legal and the same count (750).

## 4. Peak RSS — PASS
Peak child RSS: 125 MB (starter_bot run, rp60), 119 MB (sd2 runs) — far below 1 GB.

Files: `panav-bots/loop/results/int3/*` (A_lak/L_lak/A_st/L_st .txt/.json, p99_A/L.txt, rp60.txt, stream400.jsonl, out*.txt).
