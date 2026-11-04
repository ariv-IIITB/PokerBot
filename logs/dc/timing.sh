#!/bin/bash
# DC cost check: tier3 vs tier3 with a bigger discard budget, back to back (arms alternate), locks off, under the exclusive laptop lock.
cd "$(dirname "$0")/../.."
ARMS=("tier3" 'tier3:{"special_budget_frac":3.0,"discard_max_samples":16000}' 'tier3:{"special_budget_frac":5.0,"discard_max_samples":32000}')
for rep in 1 2; do for opp in maniac tier1 tier2-nolock; do for arm in "${ARMS[@]}"; do
  echo "== rep$rep $opp $arm"
  flock /tmp/pokerbot_turnstile.lock true
  flock -x /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.timing_bench --brain "$arm" --opponent "$opp" --hands 400 --variant discard_holdem --seed $rep --max-frac 1 --max-reply 5 2>&1 | grep -E "bank used|mean decision"
done; done; done
