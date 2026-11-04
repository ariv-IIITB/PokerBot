#!/bin/bash
cd "$(dirname "$0")/../.." || exit 1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
for o in "$@"; do
  [ -s logs/rd/fit_$o.pkl ] && continue
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.rd_trace $o --pairs 8 --first-seed 70000 --out logs/rd/fit_$o.pkl > logs/rd/fit_$o.log 2>&1
done
