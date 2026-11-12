# Merge tests (teammate's CFR final bot vs variants), 2026-11-12

Bots (Opps/discard, seated as d_<folder>):
- `xfinal`: the teammate's final bot (single file, unchanged). `xv3`: his first bot (v3), the baseline for the overfitting check.
- `xfin_rnr`: final + tier3x's river fold-rate mix (callers only, pmax 0.9, n0 10, min_n 10).
- `xfin_bigb`: final + `riverfold` move: an SPRT (0.45 / 0.80) on their folds to our river bets >= 0.8 pot that leave
  them chips; once "yes" (and the station trait is not), weak hands (< 0.30 equity vs their range) move part of their
  check / shove mass to a 0.85-pot bet below all-in.
- `xfin_soft`: final with a softer opponent range model (tau 0.7 -> 0.5, flat mix 0.10 -> 0.25): a sensitivity probe.
- `xprobe_polar`: a probe opponent (copy of new_eqrandom): on the river, pot bets with the top ~15% and bottom ~15%
  by equity, checks the rest.
- `xfin_shadisc`: final + a silent tier3x shadow (the bot/ and variant/ packages bundled in): tier3x follows every
  engine line and our actual actions, and chooses our discard (PIMC); any shadow error -> the final's own discard.
  Same seeds as s1a/s1b (140000) and s2a/s2b (150000), so their d_xfinal rows are its paired baseline.
- `xfin_rnr_shrange`: final + rnr + tier3x's opponent river range (Opponent.range_weights, through the shadow) in place of
  the blueprint-tracked range at every river solve (dead cards from the final's own support; exploit hook still after).
- `xfin_rnr_shtypes`: final + rnr + tier3x's X2 type posterior: each exploit trait's strength is max(its SPRT strength,
  the type-family confidence) (station -> station, prefold -> nit; overfolder/aggressor moves stay off).
  Both use seeds 140000 (Stage 1) / 150000 (Stage 2): their baseline is the d_xfin_rnr rows of s1a/s1b/s2a/s2b.
Variants are built by `lab/merge/build_variant.py BASE OUT ARM` (patches the module sources inside the bundle).

Run (resumable; skips matches already in the output file):
    PYTHONPATH=. .venv/bin/python lab/merge/arms_run.py logs/merge/OUT.jsonl --bots ... --opps ... --pairs N --hands H --bank B --seed S
Report:
    .venv/bin/python lab/merge/arms_report.py logs/merge/OUT.jsonl d_xfinal
