#!/usr/bin/env bash
# Phase F v2 evaluation driver: Tier 2 vs the TRAINING pool on discard_holdem, one step after the other
# (wall-clock budgets: never run two steps at once, never run timing checks meanwhile).
#   usage: tools/f_eval/run_f2.sh STEP [PROCESSES]
#   STEP: locks_on   100 pairs, endgame lock on   (match scores)
#         locks_off   50 pairs, lock off          (chips per hand, accounting + profile)
#         recheck     30 pairs each: base, no-E1 (discard_mode pimc), no-E2 (no tables), no-E4 (river_bluff_slope 0)
set -u
STEP=${1:?step}; PROCS=${2:-4}
cd "$(dirname "$0")/../.."
PY=.venv/bin/python
[ -f lab/opps/discard_pool.json ] || { echo "no lab/opps/discard_pool.json: the held-out split is not chosen yet (see lab/opps/discard_pool_draft.json)"; exit 2; }
mkdir -p logs/f2
run() {  # NAME BRAIN PAIRS LOCKS REPORT
  echo "start $1 $(date +%T)" >> logs/f2/progress.txt
  $PY -m lab.eval "$2" --pool train --pairs "$3" --processes "$PROCS" --locks "$4" --variant discard_holdem \
      ${5:+--report $5} --out "logs/f2/$1.txt" > "logs/f2/$1.log" 2>&1
  echo "done $1 $(date +%T)" >> logs/f2/progress.txt
}
case $STEP in
  locks_on)  run locks_on tier2 100 on accounting ;;
  locks_off) run locks_off tier2 50 off accounting,profile ;;
  recheck)
    run re_base  'tier2' 30 off accounting
    run re_noE1  'tier2:{"discard_mode":"pimc"}' 30 off
    run re_noE2  'tier2:{"use_tables":false}' 30 off
    run re_noE4  'tier2:{"river_bluff_slope":0.0}' 30 off ;;
  *) echo "unknown step $STEP"; exit 2 ;;
esac
