#!/bin/bash
# usage: run.sh TAG BRAIN PAIRS FIRST_SEED LOCKS REPORT BOT...   (one lab.eval per bot, laptop lock rules)
cd "$(dirname "$0")/../.."
tag=$1 brain=$2 pairs=$3 seed=$4 locks=$5 rep=$6; shift 6
for b in "$@"; do
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval "$brain" --pool "$b" --pairs "$pairs" \
    --first-seed "$seed" --locks "$locks" ${rep:+--report $rep} --processes 3 --variant discard_holdem \
    --out "logs/l3/${tag}_$b.txt" > "logs/l3/${tag}_$b.log" 2>&1
done
echo done > "logs/l3/${tag}.done"
