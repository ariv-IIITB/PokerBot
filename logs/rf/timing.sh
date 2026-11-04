#!/bin/bash
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/eloquent-snyder-5e78de
X='{"t3_river_narrow":true,"narrow_n0":0.001,"t3_river_rnr":true,"rnr_pmax":0.9,"rnr_n0":10,"rnr_min_n":10,"rnr_dir":-1}'
for h in 400 1000; do
  .venv/bin/python -m lab.rc_ratio --boxes 0.04 --hands $h --opponents calling_station,d_new_trapper,d_conv_opp3 --extra "$X" --seed 73900 > logs/rf/timing${h}_D4.txt 2>&1
done
