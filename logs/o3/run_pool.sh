#!/bin/bash
# O3 KEEP runs: tier3x + x_narrow + x_air_eq=.45 vs tier3x. 50 pairs, seeds 71100.., 3 processes, lowest priority.
cd "$(dirname "$0")/../.."
FLAG='tier3x:{"x_narrow":true,"x_air_eq":0.45}'
run() { # name brain locks pairs seed out-pool...
  n=$1; b=$2; l=$3; np=$4; seed=$5; shift 5
  [ -s logs/o3/$n.txt ] && grep -q "brain stats" logs/o3/$n.txt && return
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval "$b" --pool "$@" --pairs $np --first-seed $seed --locks $l --variant discard_holdem --report accounting,stats --processes 2 --out logs/o3/$n.json > logs/o3/$n.txt 2>&1
}
run pool_flag_off "$FLAG" off 50 71100 train
run pool_base_off tier3x off 50 71100 train
run pool_flag_on "$FLAG" on 50 71100 train
run pool_base_on tier3x on 50 71100 train
SIMPLE="calling_station starter tight maniac random_legal all_in"
run guard_flag "$FLAG" on 20 71600 $SIMPLE
run guard_base tier3x on 20 71600 $SIMPLE
