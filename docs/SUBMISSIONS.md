# Submissions (uploads on Unstop)

Only the user can upload. A valid upload must exist at all times (plan: after D, after E, after G
if Tier 3 ships, and the final one at H). Each zip is built by
`.venv/bin/python -m tools.package_submission --zip --stage2` (all checks run on the unpacked zip;
the zip is reproducible: same sources, same hash).

| # | Date | Phase | Commit | Zip | SHA-256 | Size | Brain | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-29 | D | `accb344` (code) | `dist/upload1_phaseD.zip` | `2dab3f52957c482556838baf9ec2e3b007a51e3ef57518640115d324cefbd42f` | 102 KB (104,606 bytes) | Tier 2 (D) | Safe Tier 2: no file reads, embedded spec/params, pacing for the 60 s / 150 s banks. Not yet uploaded: the user uploads. |

## How a zip is checked before it is handed over

1. Imports: stdlib + numpy (+ scipy lazily) only; no network/process modules; no file writes.
2. Sandbox: static scan of every packaged module for calls that read files or start processes or
   threads, and a run of the Protocol section 10 hand under an audit hook (no forbidden event).
3. Start-up under 1.0 s (launch to exit on an empty match; best of 5).
4. Smoke matches over the real protocol against the organisers' starter bot and a random bot.
5. Timing, as `python bot.py` over the real protocol, 400 hands / 60 s and 1000 hands / 150 s,
   against tier2 (lock off), maniac and the starter bot: projected 2x bank use <= 50 %, no reply
   over 0.5 s.
6. Peak memory under 500 MB.
