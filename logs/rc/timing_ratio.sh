#!/bin/bash
# usage: timing_ratio.sh HANDS BANK "B1 B2 ..." OUT   (B in seconds); off arm once per opponent, then each B back to back
H=$1; BANK=$2; BS=$3; OUT=$4
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
for opp in calling_station d_new_trapper; do
  for arm in off $BS; do
    if [ $arm = off ]; then brain=tier3; else brain="tier3:{\"t3_river_solver\":true,\"river_budget_s\":$arm}"; fi
    echo "== $opp $H h box=$arm" >> $OUT
    .venv/bin/python -m lab.timing_bench --brain "$brain" --opponent $opp --hands $H --bank $BANK --variant discard_holdem --seed 30000 2>&1 | grep -E "bank used|FORFEIT" >> $OUT
  done
done
