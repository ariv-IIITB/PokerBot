#!/bin/bash
# usage: run.sh NAME BRAIN_SPEC LOCKS PAIRS FIRSTSEED BOT...   -> logs/o3c/NAME.txt (one lab.eval per bot, back to back)
cd /home/user/PokerBot
NAME=$1; BRAIN=$2; LOCKS=$3; PAIRS=$4; SEED=$5; shift 5
P=$(( $(nproc) - 1 ))
for b in "$@"; do
  .venv/bin/python -m lab.eval "$BRAIN" --pool $b --pairs $PAIRS --first-seed $SEED --locks $LOCKS \
    --variant discard_holdem --processes $P --report accounting,stats --out logs/o3c/${NAME}_$b.txt > logs/o3c/${NAME}_$b.log 2>&1
done
echo done > logs/o3c/${NAME}.done
