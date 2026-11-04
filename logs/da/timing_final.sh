#!/bin/bash
# Final cost check: new shipped tier3 (smart + retuned) vs the old tier3 (smart off, old thresholds), back to back.
cd "$(dirname "$0")/../.."
OLD='tier3:{"smart_rollout_discard":false,"raise_equity":[0.7,0.68,0.7,0.74]}'
for rep in 1 2; do for opp in maniac tier1 tier2-nolock; do for arm in "$OLD" tier3; do
  echo "== rep$rep $opp $arm"
  .venv/bin/python -m lab.timing_bench --brain "$arm" --opponent "$opp" --hands 400 --variant discard_holdem --seed $rep --max-frac 1 --max-reply 5 2>&1
done; done; done
