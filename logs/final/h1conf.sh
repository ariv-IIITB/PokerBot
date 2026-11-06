#!/bin/bash
# H1 (x_def) 100-pair confirmation on fresh seeds 81000+: tier3x (x_def 0.5, the default) vs tier3x:{"x_def":0}.
# Chips: locks off, 100 pairs, 9 bots. Then match score: locks on, 50 pairs, same bots. One lab.eval per bot and arm.
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/final-check || exit 1
PY=/home/fioriv/synergy/PokerBot/.venv/bin/python
OUT=/home/fioriv/synergy/PokerBot/logs/final/h1conf; mkdir -p $OUT
BOTS="d_conv_opp3 d_new_rules d_new_lag d_new_trapper d_new_exploiter d_new_minraise d_conv_opp4 d_new_eqrandom d_new_geometric"
run() { # tag locks pairs arm bot
  tag=$1; locks=$2; pairs=$3; arm=$4; bot=$5
  if [ $arm = on ]; then brain='tier3x'; else brain='tier3x:{"x_def":0}'; fi
  f="$OUT/${tag}_${arm}_${bot}.txt"; [ -s "$f" ] && return
  extra=""; case $bot in d_conv_opp4|d_new_eqrandom|d_new_geometric) extra="--final";; esac
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock $PY -m lab.eval "$brain" --pool $bot --pairs $pairs --first-seed 81000 --locks $locks --variant discard_holdem --processes 3 $extra > "$f.tmp" 2>&1 && mv "$f.tmp" "$f"
}
for bot in $BOTS; do run chips off 100 on $bot; run chips off 100 off $bot; done
for arm in on off; do cat $OUT/chips_${arm}_*.txt | grep " vs " > $OUT/chips_${arm}_ALL.txt; done
for bot in $BOTS; do run score on 50 on $bot; run score on 50 off $bot; done
for arm in on off; do cat $OUT/score_${arm}_d_*.txt | grep " vs " > $OUT/score_${arm}_ALL.txt; done
echo done > $OUT/ALL_DONE
