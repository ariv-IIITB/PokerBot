#!/usr/bin/env bash
export PYTHONPATH=.
A=panav-bots/loop/cands/sub_disc_probe.py; F=panav-bots/final/bot.py; L=panav-bots/opponents/lakshya1.py; P=panav-bots/loop/reports/int2_lakshya_progress.txt; R=panav-bots/loop/results/int2
.venv/bin/python panav-bots/loop/int2/prog.py "S1 A" $A $L 40000 100 200 4 $R/lak_A_s1.json $P
.venv/bin/python panav-bots/loop/int2/prog.py "S2 A" $A $L 40000 100 500 4 $R/lak_A_s2.json $P
.venv/bin/python panav-bots/loop/int2/prog.py "S1 final" $F $L 40000 100 200 4 $R/lak_F_s1.json $P
.venv/bin/python panav-bots/loop/int2/prog.py "S2 final" $F $L 40000 100 500 4 $R/lak_F_s2.json $P
echo ALLDONE
