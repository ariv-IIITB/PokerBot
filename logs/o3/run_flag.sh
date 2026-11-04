#!/bin/bash
cd "$(dirname "$0")/../.."
while pgrep -f "eval tier3x --pool d_conv_opp3" >/dev/null; do sleep 10; done
flock /tmp/pokerbot_turnstile.lock true
nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval 'tier3x:{"x_narrow":true}' --pool d_conv_opp3 --pairs 30 --first-seed 71000 --locks off --variant discard_holdem --report accounting,profile,stats --processes 2 --out logs/o3/tier3x_narrow_opp3_locksoff.json > logs/o3/tier3x_narrow_opp3_locksoff.txt 2>&1
