#!/bin/bash
cd /home/user/PokerBot
while [ ! -f logs/o3c/queue2.done ]; do sleep 20; done
B='tier3x:{"x_narrow":true,"x_air_eq":0.45}'
run() { .venv/bin/python -m lab.opps.threebet_acct "$2" $3 40 --first-seed 71950 > logs/o3c/3bp_$1_$3.txt 2> logs/o3c/3bp_$1_$3.err; }
run base tier3x d_conv_opp3 & run base tier3x d_new_exploiter & run B "$B" d_conv_opp3 & wait
run B "$B" d_new_exploiter
echo done > logs/o3c/queue3.done
