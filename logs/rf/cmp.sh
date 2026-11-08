#!/bin/bash
# cmp.sh ARM [BASEPREFIX]  : compare ARM_* against BASE_* (3 bots)
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/eloquent-snyder-5e78de
b=${2:-BASE}
cat logs/rf/${b}_d_conv_opp3.txt logs/rf/${b}_d_new_exploiter.txt logs/rf/${b}_d_new_trapper.txt > /tmp/rf_b.txt
cat logs/rf/$1_d_conv_opp3.txt logs/rf/$1_d_new_exploiter.txt logs/rf/$1_d_new_trapper.txt > /tmp/rf_a.txt
.venv/bin/python -m lab.eval --compare /tmp/rf_b.txt /tmp/rf_a.txt
