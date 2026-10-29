#!/usr/bin/env bash
# usage: run_batch.sh SNAPSHOT_DIR PAIRS PARALLEL TASKS_FILE
# TASKS_FILE lines: NAME|tier2:{json}|OPPONENT   (one match series per line, run PARALLEL at a time).
# Writes SNAPSHOT_DIR/logs/e/NAME_<opp>.{log,txt}; summarise with: python tools/e_eval/summ.py SNAPSHOT_DIR/logs/e
# Set PY to the venv python (default: this repo's .venv).
SNAP=$1; PAIRS=$2; PAR=$3; TASKS=$4
export SNAP PAIRS PY=${PY:-$(cd "$(dirname "$0")/../.." && pwd)/.venv/bin/python}
run_one() {
  IFS='|' read -r NAME BRAIN OPP <<< "$1"
  cd "$SNAP" && "$PY" -m lab.eval "$BRAIN" --pool "$OPP" --pairs "$PAIRS" --processes 1 --locks off \
    --variant discard_holdem --report accounting --out "logs/e/${NAME}_${OPP}.txt" > "logs/e/${NAME}_${OPP}.log" 2>&1
  echo "done ${NAME}_${OPP} $(date +%T)" >> "$SNAP/logs/e/done.txt"
}
export -f run_one
grep -v '^#' "$TASKS" | grep . | xargs -d '\n' -P "$PAR" -I{} bash -c 'run_one "$1"' _ {}
