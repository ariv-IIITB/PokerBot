#!/bin/bash
# RD A/B driver, resumable: one lab.eval per (arm, bot); an existing non-empty output file is skipped.
# usage: ab.sh TAG SEED PAIRS ARMFILE   (ARMFILE: lines "name<TAB>brain-spec")
cd "$(dirname "$0")/../.." || exit 1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
TAG=$1; SEED=$2; PAIRS=$3; ARMS=$4; BOTS=${BOTS:-"d_conv_opp3 d_new_exploiter d_new_rules d_new_lag d_new_trapper d_new_minraise"}
D=logs/rd/$TAG; mkdir -p $D
ev() {  # out locks brain bot report
  [ -s "$1" ] && return 0
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval "$3" --pool $4 --pairs $PAIRS --first-seed $SEED \
      --locks $2 --processes ${PROCS:-3} --report $5 --out "$1.tmp" > /dev/null 2> "$1.err" && mv "$1.tmp" "$1"
}
for bot in $BOTS; do
  while IFS=$'\t' read -r name spec; do
    ev $D/chips_${name}_$bot.txt off "$spec" $bot accounting
  done < $ARMS
done
echo done > $D/DONE
