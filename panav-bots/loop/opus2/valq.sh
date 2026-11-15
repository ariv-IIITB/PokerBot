#!/usr/bin/env bash
# OPUS2 validation queue (resumable). Waits for the design run to finish.
export PYTHONPATH=.
while pgrep -f opus2/design.sh >/dev/null; do sleep 20; done
A=panav-bots/loop/cands/sub_disc_probe.py; L=panav-bots/loop/cands/sub_s2_lock.py; R=panav-bots/loop/results/opus2/val; mkdir -p $R
E=panav-bots/eval_bots; O=Opps/discard
declare -A P=( [lakshya1]=panav-bots/opponents/lakshya1.py [new_eqrandom]=$O/new_eqrandom/bot.py [new_trapper]=$O/new_trapper/bot.py
 [s7_solver]=$E/strong/s7_solver/bot.py [conv_opp3]=$O/conv_opp3/bot.py [eqtag]=$E/spar/eqtag/bot.py [potctl]=$E/spar/potctl/bot.py
 [polar]=$E/spar/polar/bot.py [new_geometric]=$O/new_geometric/bot.py [new_exploiter]=$O/new_exploiter/bot.py [s4_balanced]=$E/strong/s4_balanced/bot.py
 [s2_rollout]=$E/strong/s2_rollout/bot.py [s3_exploit]=$E/strong/s3_exploit/bot.py [trapper]=$E/spar/trapper/bot.py
 [s5_preflop]=$E/strong/s5_preflop/bot.py [s10_regret]=$E/strong/s10_regret/bot.py )
run() { [ -f $R/$1.json ] || timeout 7200 .venv/bin/python panav-bots/loop/opus2/duel1000.py $2 $3 --seeds $4 --first-seed $5 --hands 1000 --processes 4 --out $R/$1.json; }
for b in lakshya1 new_eqrandom new_trapper s7_solver conv_opp3 eqtag; do run A_$b $A ${P[$b]} 24 61000; run L_$b $L ${P[$b]} 24 61000; done
run h2h_L_A $L $A 40 62000
for b in potctl polar new_geometric new_exploiter s4_balanced s2_rollout s3_exploit trapper s5_preflop s10_regret; do run A_$b $A ${P[$b]} 24 61000; done
echo VALDONE
