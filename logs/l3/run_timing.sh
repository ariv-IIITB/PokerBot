#!/bin/bash
# L3 timing: tier3 vs R10 (tier3x + x_3b_ref 0.10), same hands/seed/opponent, back to back under the exclusive lock.
cd "$(dirname "$0")/../.."
for opp in d_new_trapper d_conv_opp3; do
  for brain in tier3 'tier3x:{"x_3b_ref":0.10}'; do
    echo "=== $brain vs $opp"; .venv/bin/python -m lab.timing_bench --brain "$brain" --opponent $opp --variant discard_holdem --hands 400 --seed 1 2>&1 | tail -3
  done
done
echo TIMING_DONE
