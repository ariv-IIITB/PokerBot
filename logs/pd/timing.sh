#!/bin/bash
# alternating tier3 / tier4p, 400 hands, 2x slower, back to back; run under the exclusive lock
cd "$(dirname "$0")/../.."
for b in tier3 tier4p tier3 tier4p; do for o in calling_station d_new_trapper; do
  echo "== $b $o"; .venv/bin/python -m lab.timing_bench --brain $b --opponent $o --hands 400 --bank 60 --slowdown 2 --variant discard_holdem --seed 1 2>&1 | tail -4
done; done
