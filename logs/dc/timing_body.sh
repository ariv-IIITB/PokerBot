#!/bin/bash
cd "$(dirname "$0")/../.."
ARMS=("tier3" 'tier3:{"smart_rollout_discard":false}' 'tier3:{"special_budget_frac":1.5,"discard_max_samples":8000}' 'tier3:{"special_budget_frac":2.5,"discard_max_samples":12000}' 'tier3:{"discard_learn":true}')
for rep in 1 2; do for opp in maniac tier1 tier2-nolock; do for arm in "${ARMS[@]}"; do
  echo "== rep$rep $opp $arm"
  .venv/bin/python -m lab.timing_bench --brain "$arm" --opponent "$opp" --hands 400 --variant discard_holdem --seed $rep --max-frac 1 --max-reply 5 2>&1 | grep -E "bank used|mean decision"
done; done; done
