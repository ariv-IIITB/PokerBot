#!/bin/bash
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/eloquent-snyder-5e78de
while [ ! -f logs/rf/diag2.done ]; do sleep 20; done
for opp in d_new_trapper d_new_exploiter; do
  for arm in base d1; do
    flock /tmp/pokerbot_turnstile.lock true
    nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.rf_spots $opp --arm $arm --pairs 25 --first-seed 73000 --out logs/rf/p_${opp}_${arm}.pkl > logs/rf/p_${opp}_${arm}.txt 2>&1
  done
done
echo done > logs/rf/diag3.done
