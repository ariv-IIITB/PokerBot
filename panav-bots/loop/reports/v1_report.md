# V1: final validation of L1 `probe` — verdict **FAIL** (ship final unchanged)

Builds (seeded, solver noise pinned: sample_seed=1, force_mode=NORMAL, solver_passes=715): base = `evalbuilds/final_seeded.py`;
cand = final's bot.py + L1 `botsrc.exploit.py` (cands/l1_probe2) + the same 3 keys. Unpacked-source diff base vs cand: ONLY
`botsrc.exploit.py` (probe move: weakcheck trait, _probe, counters) and CONFIG exploit += "probe". Fresh seeds 5000-5023 (bots),
5100-5123 (lakshya1, 500h legs), 5200-5215 (adversary). 24 pairs x 200h per bot, real bank (0.15 s/hand), all paired by seed.
Not run (time): strong/* bots (7). 18 non-lakshya bots were run (>= 14 required): 9 spar + 9 Opps/discard.

## Pre-registered PASS rule vs result
| # | rule | result | ok |
|---|---|---|---|
| 1 | pooled paired delta over >= 14 non-lakshya bots >= 0.0 | **+0.016 ± 0.060** (18 bots, mean of per-bot deltas) | yes (flat) |
| 2 | lakshya1, 500h legs, 24 pairs, delta >= +0.20 | base -0.43±0.31, cand +0.10±0.29, **delta +0.53 ± 0.12** (score 0.375 -> 0.604) | yes |
| 3 | no bot down > 2 SE | worst: new_lag -0.55±0.36 (z -1.5), trapper -0.28±0.27 (z -1.1) | yes |
| 4 | head-to-head cand (A) vs base, 24 pairs x 200h, delta >= 0 | **-0.09 ± 0.04** chips/hand (z -2.2), match score 0.500 | **NO** |
| 5 | 0 forfeits / illegal; worst reply <= 80 ms; bank within 5 pp | 0 forfeits in all runs; bank use base 27.7% / cand 27.3% (500h lakshya legs: 30.8% / 28.8%); see caveat | yes* |

PASS needs all five; #4 fails by the rule as written -> **FAIL**. (*) `worst_decision_s` from lab/engine.py is a harness wall-clock
under 3 parallel matches and includes protocol overhead: mean-of-worst 0.224 s (base) vs 0.224 s (cand), max 0.41 vs 0.40 s. That is
above 80 ms for BOTH builds (river solver spends its budget), so the "<= 80 ms in the bot's own timing" part could not be checked
(bot stderr is not captured by file_duel); cand is not slower than base.

## Per-bot paired deltas (cand - base, chips/hand, 24 pairs, ± SE of the paired delta)
    adapt            base  +0.46±0.28  cand  +0.89±0.32  delta  +0.44±0.17  z=+2.6 n=24
    betfold          base  +1.29±0.21  cand  +1.52±0.29  delta  +0.24±0.28  z=+0.9 n=24
    conv_opp3        base  +0.34±0.18  cand  +0.64±0.23  delta  +0.30±0.16  z=+1.9 n=24
    conv_opp4        base  +0.45±0.29  cand  +0.68±0.31  delta  +0.24±0.20  z=+1.2 n=24
    discardread      base  +0.95±0.32  cand  +0.88±0.33  delta  -0.07±0.27  z=-0.3 n=24
    donk             base  +1.05±0.32  cand  +0.85±0.36  delta  -0.20±0.30  z=-0.6 n=24
    lakshya          base  -0.43±0.31  cand  +0.10±0.29  delta  +0.53±0.12  z=+4.3 n=24
    light3b          base  +0.80±0.42  cand  +1.10±0.38  delta  +0.29±0.34  z=+0.9 n=24
    new_eqrandom     base  +0.73±0.30  cand  +0.91±0.30  delta  +0.18±0.10  z=+1.8 n=24
    new_exploiter    base  +0.40±0.22  cand  +0.21±0.26  delta  -0.19±0.20  z=-0.9 n=24
    new_geometric    base  +0.02±0.29  cand  +0.01±0.30  delta  -0.01±0.23  z=-0.0 n=24
    new_lag          base  +2.75±0.55  cand  +2.20±0.53  delta  -0.55±0.36  z=-1.5 n=24
    new_minraise     base  +0.54±0.29  cand  +0.42±0.26  delta  -0.12±0.21  z=-0.6 n=24
    new_rules        base  +0.95±0.22  cand  +1.06±0.24  delta  +0.10±0.20  z=+0.5 n=24
    new_trapper      base  +0.77±0.31  cand  +0.81±0.30  delta  +0.04±0.33  z=+0.1 n=24
    polar            base  +1.23±0.35  cand  +1.11±0.37  delta  -0.12±0.30  z=-0.4 n=24
    potctl           base  +0.61±0.30  cand  +0.47±0.34  delta  -0.14±0.23  z=-0.6 n=24
    tilt             base  +0.76±0.29  cand  +0.91±0.33  delta  +0.16±0.24  z=+0.7 n=24
    trapper          base  +1.08±0.26  cand  +0.80±0.29  delta  -0.28±0.27  z=-1.1 n=24
    POOLED non-lakshya (mean of 18 bot deltas): +0.016 ± 0.060

## Head-to-head and adversary
- cand vs base: -0.09 ± 0.04 (24 pairs x 200h). With solver noise pinned the two bots play nearly identically, so the SE is small and a
  -0.09 is not pure noise; it says the probe move costs a little against a copy of final that does not exploit it (probes into a
  non-folding, balanced checking range lose the bet when called). Small, but pre-registered as a fail.
- Scripted exploit-back adversary (`adversaries/switcher.py`: 100 hands bet wide / fold 75% to bets after checking, then checks every
  first-in spot and check-raises with pair+): base +4.92±0.50, cand +4.90±0.49 (16 pairs x 200h), 0 forfeits. No exploit-back loss for
  the probe, but the adversary is weak (both crush it), so this is a weak test; it is NOT evidence the probe is safe against a good trapper.

## Noise caveat
Per-bot SEs are 0.2-0.4 chips/hand on 24 pairs: only adapt (+0.44, z +2.6) and lakshya1 (+0.53, z +4.3) exceed 2 SE; with 20 comparisons
one z=2.6 is not surprising. Pooled +0.016 ± 0.06 = no harm, no gain on non-aggressive bots. Reruns of final are bit-reproducible only
because of the pinned seeds; lakshya1 base here is -0.43 (L1 confirm saw -0.45, dev -0.92), consistent.

## Ivey verdict for the probe move
Taking the initiative when a bot's checks are weak (it folds >= 60% to a bet after checking) is how a strong heads-up player plays:
PRINCIPLE, gated on the observed fold rate and bounded (TV <= 0.3). The data agree where the trait is real: lakshya1 +0.53 (z +4.3) and
adapt +0.44, but they do not show a general gain (pooled +0.02), and against a copy of an unexploitable final the move is a measurable
small leak (-0.09). So it behaves as SITUATIONAL (it is a trait-gated exploit, not an across-the-board improvement), and the cost of a
false positive is real. Not shown to be safe against a good opponent who checks wide and calls.

## Decision
FAIL by pre-registered rule #4 -> ship final unchanged; `candidates/final_probe.py` NOT produced. If the owner decides to ship anyway:
the evidence is +0.53 vs the one aggressive bot we know the field contains, flat elsewhere, -0.09 vs final itself; the build is
`loop/cands/l1_probe2.py` on branch loop/L1 (identical to what was tested, minus the 3 eval-only keys).
Files: results/v1/*.json|txt (raw per-pair data incl. bank_a/worst_a), tools/v1_duel.py, tools/v1_analyze.py, run_v1.sh, adversaries/switcher.py.
