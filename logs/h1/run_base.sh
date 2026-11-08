#!/bin/bash
# H1 baseline: tier3x (tier4/int defaults) and tier3, held-out bots, 100 pairs, seeds 77000-77099.
cd "$(dirname "$0")/../.."
P=$(($(nproc)-1))
for arm in "tier3x off" "tier3 off" "tier3x on" "tier3 on"; do
  set -- $arm; b=$1; l=$2
  for opp in d_conv_opp4 d_new_eqrandom d_new_geometric; do
    out=logs/h1/base_${b}_${l}_${opp}.txt
    [ -s "$out" ] && continue
    rep=""; [ "$l" = off ] && rep="--report accounting,stats,lines"
    .venv/bin/python -m lab.eval $b --pool $opp --final --pairs 100 --first-seed 77000 --locks $l \
      --variant discard_holdem --processes $P $rep --out $out > logs/h1/base_${b}_${l}_${opp}.log 2>&1
  done
done
echo done > logs/h1/base.done
