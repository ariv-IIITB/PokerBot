#!/usr/bin/env bash
# timing under slowdown 2.0 emulation vs lakshya1, full-length legs. 1 core.
export PYTHONPATH=.; R=panav-bots/loop/results/int2/sd; L=panav-bots/opponents/lakshya1.py
for B in A F; do
 .venv/bin/python panav-bots/loop/tools/int1_check.py $R/${B}_sd2.py $L --hands 400 --total 400 --bank 60 --seeds 1 --first-seed 700 | tail -1 > $R/${B}_400.json
 .venv/bin/python panav-bots/loop/tools/int1_check.py $R/${B}_sd2.py $L --hands 1000 --total 1000 --bank 150 --seeds 1 --first-seed 700 | tail -1 > $R/${B}_1000.json
done; echo TDONE
