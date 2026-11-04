#!/bin/bash
# O3C step 5: Tier 3 vs arm B (tier3x defaults), same hands/seed/opponent, back to back under the exclusive lock.
cd "$(dirname "$0")/../.."
for opp in d_conv_opp3 d_new_exploiter; do
  for brain in tier3 tier3x; do
    echo "=== $brain vs $opp"; .venv/bin/python -m lab.timing_bench --brain $brain --opponent $opp --variant discard_holdem --hands 400 --seed 1 2>&1 | tail -12
  done
done
echo TIMING_DONE
