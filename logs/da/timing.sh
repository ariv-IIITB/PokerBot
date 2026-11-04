#!/bin/bash
# DA cost check: tier3 vs tier3 + smart rollouts, back to back (arms alternate), Discard Hold'em, locks off.
cd "$(dirname "$0")/../.."
ON='tier3:{"smart_rollout_discard":true}'
for rep in 1 2; do for opp in maniac tier1 tier2-nolock; do for arm in tier3 "$ON"; do
  echo "== rep$rep $opp $arm"
  .venv/bin/python -m lab.timing_bench --brain "$arm" --opponent "$opp" --hands 400 --variant discard_holdem --seed $rep --max-frac 1 --max-reply 5
done; done; done
