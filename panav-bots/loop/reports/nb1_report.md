# NB1: final vs new_eqrandom at 500-hand legs (DRAFT, pre-registered rule written before any candidate number)

## PASS rule (pre-registered)
- DEV (new_eqrandom, seeds 800-815, 500h legs): paired delta cand-base > 2 x SE of the base-vs-base noise floor.
- Guard bots (seeds 900-911, 200h legs): pooled paired delta >= 0, no guard bot down by > 2 SE, cand-vs-base head-to-head not worse.
- Zero forfeits / illegal replies, timing within limits. Never relaxed after seeing numbers.

## Noise floor (base vs base, same seeds 800-815, 500h, two runs)
run1 -0.245 +- 0.251, score 0.469; run2 +0.150 +- 0.224, score 0.531; paired delta run2-run1 = +0.395 +- 0.195 (SD per seed 0.78).
=> a single-bot, 16-pair delta below ~0.4 chips/hand is noise. final's solver is wall-clock driven, so even same-seed runs differ.
