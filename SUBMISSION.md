# SUBMISSION: upload `bot.py`

**The file to submit is [`bot.py`](bot.py) in the repository root.** It is the only file named `bot.py`
in this repository. Every other bot (the opponents in `Opps/`, the test bots in `panav-bots/eval_bots/`,
the previous final in `panav-bots/final/`) was renamed to `main_bot.py`, and the old toolkit launcher is
`toolkit_entry.py`, so nothing else can be picked up by mistake.

| | |
|---|---|
| Run command | `python3.11 bot.py` (JSON lines on stdin/stdout, official `pokerbots` protocol; debug output goes to stderr) |
| Format | one self-contained file, 732 KB (limit 5 MB) |
| Imports | standard library and NumPy only; no file, socket or subprocess access |
| sha256 | `2309eedc310d33cb408374ac591da2e00357a85d0bf41ddb40ae0febb4362afe` |
| Check | `sha256sum bot.py` should print the line above |

## What it is
Candidate "A" = the previous final bot (`panav-bots/final/main_bot.py`: CFR blueprint, online river solver and
exploit layer) **plus** two changes: DISC1 (an equity-based discard choice) and the raw probe move. It was built
and checked in the INT2 session (branch `loop/int2`, report `panav-bots/loop/reports/int2_report.md`).

## Evidence (honest summary)
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
