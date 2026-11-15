#!/usr/bin/env bash
# OPUS1 diagnosis runs: A (sub_disc_probe) and F (final) vs new_trapper / new_eqrandom, design seeds 46000-46023, logs kept
cd "$(dirname "$0")/../../.."
R=panav-bots/loop/results/opus1/diag
mkdir -p $R
A=panav-bots/loop/cands/sub_disc_probe.py; F=panav-bots/final/bot.py
for o in new_trapper new_eqrandom; do
 for b in A F; do
  [ -f $R/${b}_$o.json ] && continue
  bot=$A; [ $b = F ] && bot=$F
  PYTHONPATH=. timeout 3000 .venv/bin/python panav-bots/loop/tools/file_duel.py $bot Opps/discard/$o/bot.py --seeds 24 --first-seed 46000 \
    --hands 200 --processes 3 --logdir $R/logs_${b}_$o --out $R/${b}_$o.json > $R/${b}_$o.txt 2>&1
  echo "$b $o $(head -1 $R/${b}_$o.txt)"
 done
done
echo DONE
