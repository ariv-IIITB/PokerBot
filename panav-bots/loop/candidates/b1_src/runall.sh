#!/usr/bin/env bash
cd /home/user/pokerbot
R=panav-bots/loop/results; E=panav-bots/eval_bots
run() { # who name path seeds
  [ -f $R/$1_$2.json ] && return
  PYTHONPATH=. timeout 1500 .venv/bin/python panav-bots/loop/tools/file_duel.py $5 $3 --seeds $4 --hands 200 --first-seed 100 --processes 3 --out $R/$1_$2.json >> /tmp/claude-0/w/runall.log 2>&1
}
for who in base cand_b1; do
  if [ $who = base ]; then BOT=panav-bots/final/bot.py; else BOT=panav-bots/loop/candidates/cand_b1.py; fi
  for b in spar/eqtag spar/trapper strong/s1_ranges strong/s2_rollout strong/s3_exploit; do run $who $(basename $b) $E/$b/bot.py 24 $BOT; done
  for b in spar/potctl spar/polar strong/s4_balanced strong/s5_preflop strong/s6_discard spar/betfold spar/light3b strong/s7_solver strong/s8_meta strong/s9_sizing spar/donk spar/adapt spar/tilt spar/discardread strong/s10_regret; do run $who $(basename $b) $E/$b/bot.py 16 $BOT; done
  for b in conv_opp3 conv_opp4 new_eqrandom new_exploiter new_geometric new_lag new_minraise new_rules new_trapper; do run $who old_$b Opps/discard/$b/bot.py 12 $BOT; done
  run $who lakshya1 panav-bots/opponents/lakshya1.py 16 $BOT
done
echo ALLDONE >> /tmp/claude-0/w/runall.log
