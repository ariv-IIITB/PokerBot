#!/bin/bash
# O3 confirmation: fresh seeds (71500.., 100 pairs), base vs kept flags, locks off and on; then the simple-bot guard.
# d_new_rules is excluded (blind set, one run at the end). Waits for the screening queue to finish first.
cd "$(dirname "$0")/../.."
while pgrep -f "logs/o3/run_screen.sh" > /dev/null; do sleep 60; done
POOL="d_conv_opp3 d_new_lag d_new_trapper d_new_exploiter d_new_minraise"
SIMPLE="calling_station starter tight maniac random_legal all_in"
KEEP='tier3x:{"x_narrow":true,"x_air_eq":0.45}'
run() { n=$1; b=$2; l=$3; np=$4; seed=$5; shift 5
  [ -s logs/o3/$n.txt ] && grep -q "brain stats" logs/o3/$n.txt && return
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval "$b" --pool "$@" --pairs $np --first-seed $seed --locks $l --variant discard_holdem --report accounting,stats --processes 2 --out logs/o3/$n.json > logs/o3/$n.txt 2>&1
}
run conf_base_off tier3x off 100 71500 $POOL
run conf_B_off "$KEEP" off 100 71500 $POOL
run conf_base_on tier3x on 100 71500 $POOL
run conf_B_on "$KEEP" on 100 71500 $POOL
run guard_base_on tier3x on 20 71800 $SIMPLE
run guard_B_on "$KEEP" on 20 71800 $SIMPLE
