#!/bin/bash
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/eloquent-snyder-5e78de
while ! { [ -s logs/rf/NA_d_new_trapper.txt ] && grep -q "brain stats" logs/rf/NA_d_new_trapper.txt; }; do sleep 20; done
B3='d_conv_opp3 d_new_exploiter d_new_trapper'
S='"x_narrow":true,"x_air_eq":0.45,"t3_river_solver":true,"river_max_iters":110,"river_box_mult":50,"river_budget_s":0.08,"t3_river_narrow":true,"t3_river_rnr":true,"t3_river_shifts":true'
logs/rf/arm.sh C1 "tier3x:{$S,\"narrow_n0\":0.001}" 30 73000 off $B3
R='"rnr_pmax":0.9,"rnr_n0":10,"rnr_min_n":10'
logs/rf/arm.sh C2 "tier3x:{$S,\"narrow_n0\":0.001,$R}" 30 73000 off $B3
logs/rf/arm.sh C3 "tier3x:{$S,\"narrow_n0\":0.001,$R,\"river_face_base\":true}" 30 73000 off $B3
