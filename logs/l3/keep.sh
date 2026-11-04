#!/bin/bash
# L3 KEEP for R10 on fresh seeds 75100-75149 (two-part), simple-bot guard 75200+, then timing.
cd "$(dirname "$0")/../.."
P5="d_conv_opp3 d_new_exploiter d_new_lag d_new_trapper d_new_minraise"
R='tier3x:{"x_3b_ref":0.10}'
logs/l3/run.sh kb_off tier3x 50 75100 off "" $P5
logs/l3/run.sh kr_off "$R" 50 75100 off "" $P5
logs/l3/run.sh kb_on tier3x 50 75100 on "" $P5
logs/l3/run.sh kr_on "$R" 50 75100 on "" $P5
logs/l3/run.sh guard "$R" 20 75200 on "" calling_station starter tight maniac random_legal all_in
flock /tmp/pokerbot_turnstile.lock flock -x /tmp/pokerbot_laptop.lock logs/l3/run_timing.sh > logs/l3/timing.txt 2>&1
echo done > logs/l3/keep.done
