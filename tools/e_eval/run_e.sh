#!/usr/bin/env bash
# usage: run_e.sh SNAPSHOT_DIR NAME 'tier2:{json}' PAIRS PROCESSES pool... ; writes SNAPSHOT_DIR/logs/e/NAME.txt
SNAP=$1; NAME=$2; BRAIN=$3; PAIRS=$4; PROCS=$5; shift 5
POOL=${@:-tier1 calling_station tight maniac starter opp3 opp4}
cd $SNAP
/home/user/PokerBot/.venv/bin/python -m lab.eval "$BRAIN" --pool $POOL --pairs $PAIRS --processes $PROCS --locks off --variant discard_holdem --report accounting --out logs/e/$NAME.txt > logs/e/$NAME.log 2>&1
echo "done $NAME $(date +%T)" >> logs/e/done.txt
