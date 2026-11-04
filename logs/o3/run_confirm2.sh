#!/bin/bash
# O3 confirmation, one lab.eval per bot (the shared lock is released between bots). Waits for the running
# 5-bot conf_base_off job. Per-bot outputs go to logs/o3/parts/, combined into logs/o3/<arm>.json/.txt.
cd "$(dirname "$0")/../.."
mkdir -p logs/o3/parts
while [ ! -s logs/o3/conf_base_off.json ]; do sleep 30; done
POOL="d_conv_opp3 d_new_lag d_new_trapper d_new_exploiter d_new_minraise"
SIMPLE="calling_station starter tight maniac random_legal all_in"
KEEP='tier3x:{"x_narrow":true,"x_air_eq":0.45}'
arm() { n=$1; b=$2; l=$3; np=$4; seed=$5; shift 5
  [ -s logs/o3/$n.json ] && return
  for o in "$@"; do
    f=logs/o3/parts/${n}__$o
    [ -s $f.txt ] && grep -q "brain stats" $f.txt && continue
    flock /tmp/pokerbot_turnstile.lock true
    nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval "$b" --pool $o --pairs $np --first-seed $seed --locks $l --variant discard_holdem --report accounting,stats --processes 2 --out $f.json > $f.txt 2>&1
  done
  cat $(for o in "$@"; do echo logs/o3/parts/${n}__$o.json; done) > logs/o3/$n.json
  cat $(for o in "$@"; do echo logs/o3/parts/${n}__$o.txt; done) > logs/o3/$n.txt
}
arm conf_B_off "$KEEP" off 100 71500 $POOL
arm conf_base_on tier3x on 100 71500 $POOL
arm conf_B_on "$KEEP" on 100 71500 $POOL
arm guard_base_on tier3x on 20 71800 $SIMPLE
arm guard_B_on "$KEEP" on 20 71800 $SIMPLE
