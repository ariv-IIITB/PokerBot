#!/bin/bash
# step 1: per spot class, 25 pairs, seeds 73000-73024, locks off
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/eloquent-snyder-5e78de
for opp in d_conv_opp3 d_new_exploiter d_new_trapper; do
  for arm in base solver na; do
    flock /tmp/pokerbot_turnstile.lock true
    nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.rf_spots $opp --arm $arm --pairs 25 --first-seed 73000 --out logs/rf/d1_${opp}_${arm}.pkl > logs/rf/d1_${opp}_${arm}.txt 2>&1
  done
done
echo done > logs/rf/diag.done
