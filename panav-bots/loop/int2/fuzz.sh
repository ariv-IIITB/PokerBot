#!/usr/bin/env bash
BOT=$1
export PYTHONPATH=.
for T in "400 60" "1000 150"; do set -- $T; for O in weird:mixed weird:random_size weird:all_in weird:min_raise weird:malformed lab/sparring/starter_bot.py; do
 .venv/bin/python panav-bots/loop/tools/int1_check.py $BOT $O --hands 200 --total $1 --bank $2 --seeds 2 2>&1 | tail -1; done; done
