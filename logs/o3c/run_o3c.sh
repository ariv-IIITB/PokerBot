#!/bin/bash
# O3C: arm B (tier3x defaults: x_narrow on, x_air_eq 0.45) vs base (both forced off) on top of tier4/int.
# One lab.eval per bot, --processes 3, nice 15, seeds 76000-76999. d_new_rules is NOT in these pools (blind set).
cd "$(dirname "$0")/../.."
POOL="d_conv_opp3 d_new_lag d_new_trapper d_new_exploiter d_new_minraise"
SIMPLE="calling_station starter tight maniac random_legal all_in"
BASE='tier3x:{"x_narrow":false,"x_air_eq":0.0}'
A='tier3x:{"x_air_eq":0.0}'
B='tier3x'
arm() { n=$1; b=$2; l=$3; np=$4; seed=$5; shift 5
  [ -s logs/o3c/$n.json ] && return
  for o in "$@"; do
    f=logs/o3c/parts76/${n}__$o
    [ -s $f.txt ] && grep -q "brain stats" $f.txt && continue
    flock /tmp/pokerbot_turnstile.lock true
    nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval "$b" --pool $o --pairs $np --first-seed $seed --locks $l --variant discard_holdem --report accounting,stats --processes 3 --out $f.json > $f.txt 2>&1
  done
  cat $(for o in "$@"; do echo logs/o3c/parts76/${n}__$o.json; done) > logs/o3c/$n.json
  cat $(for o in "$@"; do echo logs/o3c/parts76/${n}__$o.txt; done) > logs/o3c/$n.txt
}
arm s1_base_on "$BASE" on 50 76000 $POOL
arm s1_B_on "$B" on 50 76000 $POOL
arm s2_base_on "$BASE" on 20 76500 $SIMPLE
arm s2_B_on "$B" on 20 76500 $SIMPLE
arm s3_base_off "$BASE" off 50 76200 $POOL
arm s3_A_off "$A" off 50 76200 $POOL
arm s3_B_off "$B" off 50 76200 $POOL
