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
Variants are built by `lab/merge/build_variant.py BASE OUT ARM` (patches the module sources inside the bundle).

Run (resumable; skips matches already in the output file):
    PYTHONPATH=. .venv/bin/python lab/merge/arms_run.py logs/merge/OUT.jsonl --bots ... --opps ... --pairs N --hands H --bank B --seed S
Report:
    .venv/bin/python lab/merge/arms_report.py logs/merge/OUT.jsonl d_xfinal
