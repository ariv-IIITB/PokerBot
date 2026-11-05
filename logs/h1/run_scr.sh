#!/bin/bash
# H1 screen: base vs x_def arms, 30 pairs, seeds 77100-77129, locks off, one lab.eval per bot and arm.
cd "$(dirname "$0")/../.."
P=$(($(nproc)-1))
while [ ! -s logs/h1/base_tier3_off_d_new_geometric.txt ]; do sleep 30; done
pkill -f run_base.sh; sleep 2; pkill -f "first-seed 77000 --locks on"
declare -A ARM=( [base]='tier3x' [D1]='tier3x:{"x_def":0.5,"x_def_margin":0.05}' [D3]='tier3x:{"x_def":0.3}' )
for opp in d_new_geometric d_conv_opp4 d_new_eqrandom d_conv_opp3 d_new_rules d_new_lag d_new_trapper d_new_exploiter d_new_minraise; do
  for a in base D1 D3; do
    out=logs/h1/scr/${a}_${opp}.txt
    [ -s "$out" ] && continue
    .venv/bin/python -m lab.eval "${ARM[$a]}" --pool $opp --final --pairs 30 --first-seed 77100 --locks off \
      --variant discard_holdem --processes $P --out $out > logs/h1/scr/${a}_${opp}.log 2>&1
  done
done
echo done > logs/h1/scr.done
nohup logs/h1/run_base.sh > logs/h1/run_base.out 2>&1 &
