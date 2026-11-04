#!/bin/bash
cd /home/user/PokerBot
while [ ! -f logs/o3c/queue3.done ]; do sleep 20; done
logs/o3c/run.sh A_on 'tier3x:{"x_narrow":true}' on 100 71500 d_conv_opp3 d_new_lag d_new_trapper d_new_exploiter d_new_minraise
echo done > logs/o3c/queue4.done
