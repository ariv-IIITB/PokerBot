#!/bin/bash
cd "$(dirname "$0")/../.."
flock /tmp/pokerbot_turnstile.lock true
nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval 'tier3x:{"x_narrow":true,"x_air_eq":0.45}' --pool d_conv_opp3 --pairs 30 --first-seed 71000 --locks off --variant discard_holdem --report accounting,profile,stats --processes 1 --out logs/o3/tier3x_narrow_air_opp3_locksoff.json > logs/o3/tier3x_narrow_air_opp3_locksoff.txt 2>&1
