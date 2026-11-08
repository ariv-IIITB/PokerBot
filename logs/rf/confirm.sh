#!/bin/bash
# 50 pairs, fresh seeds 73100-73149, the five training bots, BASE and D4 back to back per bot; locks off then on
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/eloquent-snyder-5e78de
BASE='tier3x:{"x_narrow":true,"x_air_eq":0.45}'
S0='"x_narrow":true,"x_air_eq":0.45,"t3_river_solver":true,"river_max_iters":110,"river_box_mult":50,"river_budget_s":0.08'
R='"t3_river_rnr":true,"rnr_pmax":0.9,"rnr_n0":10,"rnr_min_n":10,"rnr_dir":-1'
D4="tier3x:{$S0,\"t3_river_narrow\":true,\"narrow_n0\":0.001,$R}"
for locks in off on; do
  for bot in d_conv_opp3 d_new_trapper d_new_exploiter d_new_lag d_new_minraise; do
    logs/rf/arm.sh K_BASE_$locks "$BASE" 50 73100 $locks $bot
    logs/rf/arm.sh K_D4_$locks "$D4" 50 73100 $locks $bot
  done
done
echo done > logs/rf/confirm.done
