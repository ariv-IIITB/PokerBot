# Submissions (uploads on Unstop)

Only the user can upload. A valid upload must exist at all times (plan: after D, after E, after G
if Tier 3 ships, and the final one at H). Each zip is built by
`.venv/bin/python -m tools.package_submission --zip --stage2` (all checks run on the unpacked zip;
the zip is reproducible: same sources, same hash).

| # | Date | Phase | Commit | Zip | SHA-256 | Size | Brain | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-29 | D | `accb344` (code) | `dist/upload1_phaseD.zip` | `2dab3f52957c482556838baf9ec2e3b007a51e3ef57518640115d324cefbd42f` | 102 KB (104,606 bytes) | Tier 2 (D) | Safe Tier 2: no file reads, embedded spec/params, pacing for the 60 s / 150 s banks. Not yet uploaded: the user uploads. |
| 2 | 2026-10-29 | E | see git log (`phase E` commits) | `dist/upload2_phaseE.zip` | `1baec44f9ac2da6b2db8382ae1cba452036eccdd1c6ef9100ad3d698337bf419` | 113 KB (115,417 bytes) | Tier 2 (E, **no tables**) | **Superseded by #3: built without the embedded tables** (data/ was missing at build time). Fast discard, embedded tables, river bluff-catch slope 0.5, pacing safety 5.5. Beats upload #1's config +0.68 ± 0.26 chips/hand (50 pairs). `dist/` is not in git: rebuild with `python -m tools.package_submission --zip --stage2`. |
| 3 | 2026-10-29 | F0 | see git log (`phase F0` commits) | `dist/upload3_phaseF0.zip` | `38705aa4ea41b5450169243b905c94c49f28872d946b4d9db6831cf75f3dc108` | 169 KB (173,299 bytes) | Tier 2 (F0) | Upload #2's bot with the embedded tables (191 KB `embedded.py`) and `aggr_call_shift` 0 (`docs/reports/TIER2_VS_TIER1.md`). Package checks pass, projected 2x bank use 32-40 %. Rebuild only with `data/discard_holdem/` present (the builder now refuses otherwise). |
| 4 | 2026-10-30 | G | see git log (`phase G` commits) | `dist/upload4_phaseG.zip` | `b2a068003ea4cbe337c3a91973c2e6a58e47701fc12948d024a65995ce89eb29` | 190 KB (194,447 bytes) | **Tier 3** (G8) | Default brain tier3 (passed G8: vs Tier 2 locks on 0.670 ± 0.033; training pool locks on +1.57 ± 0.54 chips/hand, mean match score 0.62 vs 0.55; held-out +1.16 ± 0.50; `docs/reports/TIER3.md`). Tables embedded (rebuilt with `lab.precompute --samples 6000 --range-top 0.3`). Package checks pass, projected 2x bank use 27-33 %. Not yet uploaded: the user uploads. |

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
