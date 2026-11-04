#!/bin/bash
cd /home/user/PokerBot
while [ ! -f logs/o3c/base_off.done ]; do sleep 20; done
BOTS="d_conv_opp3 d_new_lag d_new_trapper d_new_exploiter d_new_minraise"
B='tier3x:{"x_narrow":true,"x_air_eq":0.45}'
logs/o3c/run.sh B_off "$B" off 100 71500 $BOTS
logs/o3c/run.sh base_on tier3x on 100 71500 $BOTS
logs/o3c/run.sh B_on "$B" on 100 71500 $BOTS
logs/o3c/run.sh guard_B "$B" on 20 71800 calling_station starter tight maniac random_legal all_in
logs/o3c/run.sh rules_base tier3x off 50 71900 d_new_rules
logs/o3c/run.sh rules_B "$B" off 50 71900 d_new_rules
echo done > logs/o3c/queue.done
