#!/bin/bash
# DISC1 pass-rule matches: base vs cand against 18 bots, paired seeds 9100..9139 (200h legs), results in results/disc1/
cd /home/user/pokerbot
BASE=panav-bots/loop/evalbuilds/final_seeded.py; CAND=panav-bots/loop/evalbuilds/final_disc_seeded.py
OUT=panav-bots/loop/results/disc1
run() { # name path seeds hands firstseed
  for v in base cand; do
    f=$BASE; [ $v = cand ] && f=$CAND
    [ -s $OUT/$1_$v.json ] && continue
    PYTHONPATH=. timeout 3000 .venv/bin/python panav-bots/loop/tools/file_duel.py $f $2 --seeds $3 --first-seed $5 --hands $4 --processes 3 --out $OUT/$1_$v.json > $OUT/$1_$v.txt 2>&1
  done
}
for b in trapper potctl polar betfold light3b donk adapt tilt discardread; do run spar_$b panav-bots/eval_bots/spar/$b/bot.py 40 200 9100; done
for b in conv_opp3 conv_opp4 new_eqrandom new_exploiter new_geometric new_lag new_minraise new_rules new_trapper; do run opps_$b Opps/discard/$b/bot.py 40 200 9100; done
touch $OUT/ALL200.done
# head-to-head cand vs base
[ -s $OUT/h2h.json ] || PYTHONPATH=. timeout 3000 .venv/bin/python panav-bots/loop/tools/file_duel.py $CAND $BASE --seeds 40 --first-seed 9100 --hands 200 --processes 3 --out $OUT/h2h.json > $OUT/h2h.txt 2>&1
# 500-hand legs (Stage 2 length)
run lakshya1_500 panav-bots/opponents/lakshya1.py 24 500 9200
run new_eqrandom_500 Opps/discard/new_eqrandom/bot.py 24 500 9200
touch $OUT/ALL.done
