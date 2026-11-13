#!/usr/bin/env bash
# runset.sh TAG BUILD.py FIRSTSEED PAIRS HANDS OUTDIR BOT1.py BOT2.py ...   (one file_duel per bot, sequential)
TAG=$1; B=$2; FS=$3; P=$4; H=$5; OUT=$6; shift 6
mkdir -p $OUT/$TAG
for bot in "$@"; do
  n=$(basename $(dirname $bot)); [ "$n" = "opponents" ] && n=$(basename $bot .py)
  [ -f $OUT/$TAG/$n.json ] && continue
  PYTHONPATH=. timeout 3000 .venv/bin/python panav-bots/loop/tools/file_duel.py $B $bot --seeds $P --hands $H --processes 3 --first-seed $FS --out $OUT/$TAG/$n.json > $OUT/$TAG/$n.txt 2>&1
done
