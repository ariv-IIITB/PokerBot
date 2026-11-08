#!/bin/bash
# Final-bot combination test: every arm vs each given bot, back to back on THIS machine (arms are only
# compared within one machine). Usage: lab/combo_run.sh PAIRS FIRST_SEED LOCKS BOT [BOT ...]
# Output: logs/combo/<locks>/<arm>__<bot>.txt (an existing non-empty file is skipped, so it resumes).
cd "$(dirname "$0")/.."
PAIRS=$1; SEED=$2; LOCKS=$3; shift 3
PROC=$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))
declare -A ARMS=(
  [base]='tier3x'
  [fast]='tier3x:{"oppstats_gate":5,"oppstats_strength":10}'
  [noovf]='tier3x:{"x_of_tr":false,"x_oft_enabled":false}'
  [nosolver]='tier3x:{"t3_river_solver":false}'
  [hide]='tier3x:{"hide_discard":true}'
)
ORDER=${ORDER:-"base fast noovf nosolver hide"}   # override: ORDER="base hide" lab/combo_run.sh ...
mkdir -p logs/combo/$LOCKS
for bot in "$@"; do
  for arm in $ORDER; do
    f=logs/combo/$LOCKS/${arm}__${bot}.txt
    [ -s "$f" ] && continue
    .venv/bin/python -m lab.eval "${ARMS[$arm]}" --pool $bot --pairs $PAIRS --first-seed $SEED --hands 200 --bank 30 \
      --locks $LOCKS --variant discard_holdem --processes $PROC --report stats > "$f.tmp" 2>&1 && mv "$f.tmp" "$f"
    echo "$(date -u +%H:%M) $arm $bot: $(grep -m1 'chips/hand' "$f" | cut -d'|' -f1,2)"
  done
done
echo COMBO_DONE
