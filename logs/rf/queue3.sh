#!/bin/bash
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/eloquent-snyder-5e78de
B3='d_conv_opp3 d_new_exploiter d_new_trapper'
S0='"x_narrow":true,"x_air_eq":0.45,"t3_river_solver":true,"river_max_iters":110,"river_box_mult":50,"river_budget_s":0.08'
logs/rf/arm.sh D1 "tier3x:{$S0,\"t3_river_narrow\":true,\"narrow_n0\":0.001}" 30 73000 off $B3
logs/rf/arm.sh D2 "tier3x:{$S0,\"t3_river_narrow\":true,\"narrow_n0\":0.001,\"river_face_base\":true}" 30 73000 off $B3
logs/rf/arm.sh D3 "tier3x:{$S0,\"t3_river_narrow\":true,\"t3_river_rnr\":true,\"t3_river_shifts\":true,\"narrow_n0\":0.001,\"river_face_base\":true}" 30 73000 off $B3
echo done > logs/rf/queue3.done
