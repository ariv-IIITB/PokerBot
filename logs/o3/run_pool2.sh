#!/bin/bash
# After run_pool.sh: the same pool/guard runs for the three-flag config (x_stab on top).
cd "$(dirname "$0")/../.."
while pgrep -f "logs/o3/run_pool.sh" >/dev/null; do sleep 30; done
STAB='tier3x:{"x_narrow":true,"x_air_eq":0.45,"x_stab":true}'
run() { n=$1; b=$2; l=$3; np=$4; seed=$5; shift 5
  [ -s logs/o3/$n.txt ] && grep -q "brain stats" logs/o3/$n.txt && return
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval "$b" --pool "$@" --pairs $np --first-seed $seed --locks $l --variant discard_holdem --report accounting,stats --processes 2 --out logs/o3/$n.json > logs/o3/$n.txt 2>&1
}
run pool_stab_off "$STAB" off 50 71100 train
run pool_stab_on "$STAB" on 50 71100 train
run guard_stab "$STAB" on 20 71600 calling_station starter tight maniac random_legal all_in
