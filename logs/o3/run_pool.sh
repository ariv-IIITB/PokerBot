#!/bin/bash
# O3 pool KEEP runs: 50 pairs, seeds 71100.., --pool train, 2 processes, lowest priority. Order: flag on first (early warning).
cd "$(dirname "$0")/../.."
run() { # name brain locks
  [ -s logs/o3/pool_$1.txt ] && grep -q "brain stats" logs/o3/pool_$1.txt && return
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.eval "$2" --pool train --pairs 50 --first-seed 71100 --locks $3 --variant discard_holdem --report accounting,stats --processes 2 --out logs/o3/pool_$1.json > logs/o3/pool_$1.txt 2>&1
}
run narrow_off 'tier3x:{"x_narrow":true}' off
run base_off tier3x off
run narrow_on 'tier3x:{"x_narrow":true}' on
run base_on tier3x on
