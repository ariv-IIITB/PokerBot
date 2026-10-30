#!/usr/bin/env bash
# Phase G ablation: tier3 with one flag off at a time vs non-pool opponents (locks off).
# Usage: [FIRST_SEED=n] tools/g_eval/ablate.sh OUTDIR PAIRS OPP[,OPP...] NAME=CONFIGJSON ...  (CONFIGJSON "tier2" = plain Tier 2)
set -u
out=$1; pairs=$2; pool=$3; shift 3
mkdir -p "$out"
for spec in "$@"; do
  name=${spec%%=*}; conf=${spec#*=}
  brain="tier3"; [ "$conf" = "tier2" ] && brain="tier2" && conf=""
  [ -n "$conf" ] && brain="$brain:$conf"
  .venv/bin/python -m lab.eval "$brain" --pool $(echo "$pool" | tr ',' ' ') --pairs "$pairs" --locks off \
    --first-seed "${FIRST_SEED:-0}" --variant discard_holdem --report accounting,profile --out "$out/$name.txt" > "$out/$name.run" 2>&1
  echo "done $name"; grep "chips/hand" "$out/$name.run" | sed 's/|.*errors/ |/' 
done
