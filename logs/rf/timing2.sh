#!/bin/bash
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/eloquent-snyder-5e78de
X='{"t3_river_narrow":true,"narrow_n0":0.001,"t3_river_rnr":true,"rnr_pmax":0.9,"rnr_n0":10,"rnr_min_n":10,"rnr_dir":-1}'
for s in 73901 73902; do
  .venv/bin/python -m lab.rc_ratio --boxes 0.04 --hands 400 --opponents calling_station --extra "$X" --seed $s
done > logs/rf/timing400_cs_rerun.txt 2>&1
