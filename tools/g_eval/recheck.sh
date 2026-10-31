#!/usr/bin/env bash
# G8 re-check after the Tier 3 deadline fix (ba5800f), one eval at a time, fresh seeds, locks on.
# Usage: [PY=python] tools/g_eval/recheck.sh [OUTDIR]   (default logs/g/recheck)
set -u
out=${1:-logs/g/recheck}
mkdir -p "$out"
PY=${PY:-.venv/bin/python}
run() { echo "start $1 $(date +%H:%M:%S)"; shift; "$PY" -m lab.eval "$@" > /dev/null 2>"$out/stderr.log.tmp"; cat "$out/stderr.log.tmp" >> "$out/stderr.txt"; rm -f "$out/stderr.log.tmp"; }
run h2h tier3 --pool tier2 --pairs 100 --first-seed 7000 --locks on --variant discard_holdem \
  --report stats --processes 8 --out "$out/h2h.txt"
run pool_t2 tier2 --pool train --pairs 50 --first-seed 8000 --locks on --variant discard_holdem \
  --report accounting,stats --processes 5 --out "$out/pool_t2.txt"
run pool_t3 tier3 --pool train --pairs 50 --first-seed 8000 --locks on --variant discard_holdem \
  --report accounting,stats --processes 5 --out "$out/pool_t3.txt"
"$PY" -m lab.eval --compare "$out/pool_t2.txt" "$out/pool_t3.txt" > "$out/compare.txt"
echo "done $(date +%H:%M:%S)"
grep -h "chips/hand\|brain stats" "$out"/h2h.txt "$out"/pool_t2.txt "$out"/pool_t3.txt
cat "$out/compare.txt"
