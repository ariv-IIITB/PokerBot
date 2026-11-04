#!/bin/bash
# cmpk.sh LOCKS : K_D4 vs K_BASE over the five bots
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/eloquent-snyder-5e78de
for a in BASE D4; do : > /tmp/rf_$a.txt; for b in d_conv_opp3 d_new_trapper d_new_exploiter d_new_lag d_new_minraise; do cat logs/rf/K_${a}_$1_$b.txt >> /tmp/rf_$a.txt 2>/dev/null; done; done
.venv/bin/python -m lab.eval --compare /tmp/rf_BASE.txt /tmp/rf_D4.txt
