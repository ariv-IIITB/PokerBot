#!/usr/bin/env bash
# usage: l2_suite.sh LABEL CAND.py BOT_LIST_FILE   (runs base final and CAND on seeds 100-111, 200-hand legs; base cached)
cd /home/user/pokerbot
LABEL=$1; CAND=$2; LIST=$3
mkdir -p panav-bots/loop/results/suite /tmp/l2/suite
while read -r NAME PATH_; do
  for V in base $LABEL; do
    if [ "$V" = base ]; then BOT=panav-bots/final/bot.py; else BOT=$CAND; fi
    OUT=panav-bots/loop/results/suite/l2_${V}_${NAME}.json
    [ "$V" = base ] && [ -f "$OUT" ] && continue
    mkdir -p /tmp/l2/suite/${V}_${NAME}
    PYTHONPATH=. timeout 1500 .venv/bin/python panav-bots/loop/tools/l2_duel.py $BOT $PATH_ --seeds 12 --first-seed 100 --hands 200 --processes 3 --logdir /tmp/l2/suite/${V}_${NAME} --out $OUT > /tmp/l2/suite/${V}_${NAME}.out 2>&1
  done
done < $LIST
echo done > /tmp/l2/suite/${LABEL}_done
