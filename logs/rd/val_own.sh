#!/bin/bash
cd "$(dirname "$0")/../.." || exit 1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
for o in "$@"; do
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.rd_trace $o --pairs 4 --first-seed 70100 --out logs/rd/val_$o.pkl > logs/rd/val_$o.log 2>&1
done
