#!/bin/bash
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/eloquent-snyder-5e78de
B3='d_new_trapper d_new_exploiter d_conv_opp3'
S0='"x_narrow":true,"x_air_eq":0.45,"t3_river_solver":true,"river_max_iters":110,"river_box_mult":50,"river_budget_s":0.08'
R='"t3_river_rnr":true,"rnr_pmax":0.9,"rnr_n0":10,"rnr_min_n":10,"rnr_dir":-1'
logs/rf/arm.sh D4 "tier3x:{$S0,\"t3_river_narrow\":true,\"narrow_n0\":0.001,$R}" 30 73000 off $B3
echo done > logs/rf/queue4.done
