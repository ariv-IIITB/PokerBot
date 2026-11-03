#!/bin/bash
# Gate R driver, resumable: one lab.eval per (step, arm, bot); an existing non-empty output file is skipped.
# Laptop stand-in for the 2x server: box ceiling and multiplier halved (shipped: 0.040 s, x3.9).
cd "$(dirname "$0")/../.." || exit 1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
ON='tier3:{"t3_river_solver":true,"river_budget_s":0.020,"river_box_mult":1.95}'
OFF='tier3'
PAIRS=${PAIRS:-50}; SEED=30000; D=logs/rc/gate
ev() {  # out locks pairs brain pool report
  [ -s "$1" ] && return 0
  flock /tmp/pokerbot_turnstile.lock true
  flock -s /tmp/pokerbot_laptop.lock nice -n 15 .venv/bin/python -m lab.eval "$4" --pool $5 --pairs $3 --first-seed $SEED \
      --locks $2 --processes 6 --report $6 --out "$1.tmp" > /dev/null 2> "$1.err" && mv "$1.tmp" "$1"
  git add "$1" 2>/dev/null; git commit -qm "RC gate R: $(basename $1)" 2>/dev/null || true
}
# 1. head to head (locks on, the match score)
ev $D/h2h_on.txt on $PAIRS "$ON" tier3 stats
# 2. training pool, both arms back to back per bot: chips (locks off, accounting) then score (locks on)
for bot in d_conv_opp3 d_new_exploiter d_new_rules d_new_lag d_new_trapper d_new_minraise; do
  ev $D/chips_on_$bot.txt  off $PAIRS "$ON"  $bot accounting,stats
  ev $D/chips_off_$bot.txt off $PAIRS "$OFF" $bot accounting
  ev $D/score_on_$bot.txt  on  $PAIRS "$ON"  $bot stats
  ev $D/score_off_$bot.txt on  $PAIRS "$OFF" $bot stats
done
echo done > $D/DONE
