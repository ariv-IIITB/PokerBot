# SUBMISSION: upload `bot.py`

**The file to submit is [`bot.py`](bot.py) in the repository root.** It is the only file named `bot.py`
in this repository. Every other bot (the opponents in `Opps/`, the test bots in `panav-bots/eval_bots/`,
the previous final in `panav-bots/final/`) was renamed to `main_bot.py`, and the old toolkit launcher is
`toolkit_entry.py`, so nothing else can be picked up by mistake.

| | |
|---|---|
| Run command | `python3.11 bot.py` (JSON lines on stdin/stdout, official `pokerbots` protocol; debug output goes to stderr) |
| Format | one self-contained file, 739 KB (limit 5 MB) |
| Imports | standard library and NumPy only; no file, socket or subprocess access |
| sha256 | `333a552fd37c203ae997f3b564fa450c968ea6ca6886ce59700415b051695ddb` |
| Check | `sha256sum bot.py` should print the line above |

## What it is
Candidate "A + probe exit + Stage 2 lock" (OPUS1 + OPUS2 combined, chosen by the owner). Candidate "A" = the previous final bot (`panav-bots/final/main_bot.py`: CFR blueprint, online river solver and
exploit layer) **plus** two changes: DISC1 (an equity-based discard choice) and the raw probe move. It was built
and checked in the INT2 session (branch `loop/int2`, report `panav-bots/loop/reports/int2_report.md`).
On top of A, `bot.py` adds a **Stage 2 risk-capped match lock** (OPUS2, branch `loop/opus2`, report `panav-bots/loop/reports/opus2_report.md`, safety report `loop/int3`): it activates only when `init.total_hands >= 800` (Stage 2); once the match lead exceeds twice the hands left it never risks more than the lead can spare, so the match cannot be lost. In Stage 1 it plays like A except for the probe exit below.
`bot.py` also contains OPUS1's **probe exit** (branch `loop/opus1`, `probe_exit: on`): the probe move switches off when the opponent's observed fold rate to our turn bets shows it is trap-style (SPRT), aimed at `new_trapper`-type bots. The OPUS1 + OPUS2 combination was built by OPUS2 (`loop/opus2`, `panav-bots/submission/bot_stage2_opus1_opus2.py`); fuzz and protocol checks are clean, but the combination itself has **no match validation**, and OPUS1's fix alone showed no pooled gain on 12 helper bots (A 154/264 vs v2 151/264) apart from a better `new_trapper` result. Rollback: the lock-only build (sha256 5855fc7a8282b8a1971eb4205737a246c6571435334b6ddb136fa4967458fd85) is saved as `panav-bots/submission_alternatives/lock_only_5855fc7a.py`; copy it to `bot.py` to use it.

## Evidence (honest summary)
- Stage 2 lock, 1000-hand single-process matches: 220/360 (61.1%) -> 263/360 (73.1%) match wins over 15 bots (+11.9 +- 1.7 points, replay estimator); real build +9.7 +- 5.2 points over 6 bots, 74/96 vs 61/96 over 4 more bots; head-to-head against A 30/40 (75%). Cost: chips/hand -0.37 raw (-0.25 capped), because the bot stops pressing once safely ahead. Timing at 2x slowdown: worst reply 0.44 s, bank <= 104 s of 150 s (A is at the same level); fuzz 0 illegal / 0 forfeits.
- The numbers below are for A (Stage 1 behaviour is identical).
- 7 opponents x 24 duplicate pairs, 200-hand legs, normal builds: **110/168 match wins (65.5%)** against 86/168 (51.2%) for the previous final (paired +14.3 +- 5.5 points).
- Against `lakshya1` (100 matches each): 56/100 at 200-hand legs and 55/100 at 500-hand legs; the previous final scored 50/100 at 200-hand legs.
- Probe alone, 30 bots x 40 pairs on fresh seeds: 62.7% -> 68.5% match wins (+5.9 +- 1.55 points).
- Safety: legality fuzz 0 illegal replies and 0 forfeits at both match lengths; worst reply 708 ms under a 2x slowdown emulation (limit 1.5 s); peak memory about 130 MB; static sandbox scan clean; first reply 0.35 s after launch.
- Known weaknesses: trapper-type opponents (`new_trapper`: 6/24 against 12/24 for the previous final); it wins only 17/40 head-to-head against the previous final. Numpy must be available in the contest Python, otherwise the bot runs in a degraded fallback mode.
- Not yet run: the six sealed holdout bots (branches `holdout/*`).

## Other candidates (not in `bot.py`)
Branches `loop/opus1` (trapper fix, partial), `loop/opus2` (Stage 2 match lock, partial), `loop/int2` (this bot and the
without-probe variant `bot_without_probe.py`), `loop/disc1`, `loop/call1`, `loop/val1`, `loop/meta1`, `loop/probeval`.

## Rebuild / verify
```bash
sha256sum bot.py
printf '{"type":"init","total_hands":400,"time_bank_ms":60000}\n' | python3.11 bot.py   # prints a ready banner to stderr
```
