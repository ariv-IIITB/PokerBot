#!/bin/bash
# usage: arm.sh NAME 'BRAIN[:JSON]' PAIRS FIRSTSEED LOCKS BOT...   one lab.eval per bot, laptop lock rules
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/eloquent-snyder-5e78de
n=$1; b=$2; np=$3; seed=$4; locks=$5; shift 5
for bot in "$@"; do
  f=logs/rf/${n}_${bot}.txt
  [ -s $f ] && grep -q "brain stats" $f && continue
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval "$b" --pool $bot --pairs $np --first-seed $seed --locks $locks --variant discard_holdem --report accounting,stats --processes 3 --out logs/rf/${n}_${bot}.json > $f 2>&1
done
