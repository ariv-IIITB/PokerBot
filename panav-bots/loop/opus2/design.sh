#!/usr/bin/env bash
export PYTHONPATH=.
A=panav-bots/loop/cands/sub_disc_probe.py; R=panav-bots/loop/results/opus2/design
for O in strong/s6_discard OPP:conv_opp4 OPP:new_minraise; do
  case $O in OPP:*) P=Opps/discard/${O#OPP:}/bot.py; N=${O#OPP:};; *) P=panav-bots/eval_bots/$O/bot.py; N=$(basename $O);; esac
  [ -f $R/A_$N.json ] || .venv/bin/python panav-bots/loop/opus2/duel1000.py $A $P --seeds 16 --first-seed 60000 --hands 1000 --processes 4 --out $R/A_$N.json
done
echo DESIGNDONE
