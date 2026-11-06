#!/bin/bash
# Final check: tier3x (the packaged default) vs every bot, locks on, 40 pairs x 400 hands, seeds 80000+.
# Then plain tier3 (upload #4's brain) on the nine LLM bots for the delta. One lab.eval per bot.
cd /home/fioriv/synergy/PokerBot/.claude/worktrees/final-check || exit 1
PY=/home/fioriv/synergy/PokerBot/.venv/bin/python
OUT=/home/fioriv/synergy/PokerBot/logs/final
run() { # brain opp extra...
  b=$1; o=$2; shift 2
  f="$OUT/${b}__${o}.txt"; [ -s "$f" ] && return
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 15 flock -s /tmp/pokerbot_laptop.lock $PY -m lab.eval $b --pool $o --pairs 40 --first-seed 80000 --locks on --variant discard_holdem --processes 3 "$@" > "$f.tmp" 2>&1 && mv "$f.tmp" "$f"
}
LLM="d_conv_opp3 d_new_rules d_new_lag d_new_trapper d_new_exploiter d_new_minraise"
HELD="d_conv_opp4 d_new_eqrandom d_new_geometric"
SIMPLE="calling_station tight maniac random_legal all_in starter tier1"
for o in $LLM $SIMPLE; do run tier3x $o; done
for o in $HELD; do run tier3x $o --final; done
for o in $LLM; do run tier3 $o; done
for o in $HELD; do run tier3 $o --final; done
echo done > $OUT/ALL_DONE
