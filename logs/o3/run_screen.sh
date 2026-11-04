#!/bin/bash
# O3 screening: 50 pairs, seeds 71100.., locks off, 2 processes, nice 15. d_new_rules is excluded (blind set).
cd "$(dirname "$0")/../.."
POOL="d_conv_opp3 d_new_lag d_new_trapper d_new_exploiter d_new_minraise"
run() { n=$1; b=$2; l=$3; np=$4; seed=$5; shift 5
  [ -s logs/o3/$n.txt ] && grep -q "brain stats" logs/o3/$n.txt && return
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval "$b" --pool "$@" --pairs $np --first-seed $seed --locks $l --variant discard_holdem --report accounting,stats --processes 2 --out logs/o3/$n.json > logs/o3/$n.txt 2>&1
}
run scr_base tier3x off 50 71100 $POOL
run scr_B 'tier3x:{"x_narrow":true,"x_air_eq":0.45}' off 50 71100 $POOL
run scr_C 'tier3x:{"x_narrow":true,"x_air_eq":0.45,"x_stab":true}' off 50 71100 $POOL
run scr_A 'tier3x:{"x_narrow":true}' off 50 71100 $POOL
