#!/usr/bin/env bash
# combined (C) vs A, 50 x 1000-hand matches per opponent, chunks of 10 seeds, alternating builds
export PYTHONPATH=.
C=panav-bots/submission/bot_stage2_opus1_opus2.py; A=panav-bots/loop/cands/sub_disc_probe.py; R=panav-bots/loop/results/opus2/final50
for spec in lakshya1:panav-bots/opponents/lakshya1.py new_eqrandom:Opps/discard/new_eqrandom/bot.py new_trapper:Opps/discard/new_trapper/bot.py trapper:panav-bots/eval_bots/spar/trapper/bot.py; do
 o=${spec%%:*}; p=${spec#*:}
 for k in 0 1 2 3 4; do s=$((64000 + 10*k))
  for b in C; do eval bot=\$$b
   [ -f $R/${b}_${o}_$k.json ] || .venv/bin/python panav-bots/loop/opus2/duel1000.py $bot $p --seeds 10 --first-seed $s --hands 1000 --processes 4 --out $R/${b}_${o}_$k.json > /dev/null 2>&1
  done
  echo "CHUNK $o $k"
 done
done
echo F50DONE
