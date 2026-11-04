#!/bin/bash
# Gate R extension: conv_opp3 and exploiter, 50 more pairs on fresh seeds 30100-30149, locks off, accounting. Resumable.
cd "$(dirname "$0")/../.." || exit 1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
ON='tier3:{"t3_river_solver":true,"river_budget_s":0.080,"river_box_mult":50,"river_max_iters":110}'
D=logs/rc/ext
ev() {  # out brain bot
  [ -s "$1" ] && return 0
  flock /tmp/pokerbot_turnstile.lock true
  flock -s /tmp/pokerbot_laptop.lock nice -n 15 .venv/bin/python -m lab.eval "$2" --pool $3 --pairs 50 --first-seed 30100 \
      --locks off --processes 3 --report accounting --out "$1.tmp" > /dev/null 2> "$1.err" && mv "$1.tmp" "$1"
}
for bot in d_conv_opp3 d_new_exploiter; do
  ev $D/on_$bot.txt "$ON" $bot
  ev $D/off_$bot.txt tier3 $bot
done
echo done > $D/DONE
