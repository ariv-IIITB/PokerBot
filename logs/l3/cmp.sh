#!/bin/bash
# cmp.sh BASE ARM: per-bot chips + the 3bet_opp line, then lab.eval --compare on the summary lines
cd "$(dirname "$0")"
for f in $1_d_*.txt; do b=${f#$1_}; [ -f "$2_$b" ] || continue; echo "== ${b%.txt}"; for t in $1 $2; do
  printf "%-5s %s | %s\n" $t "$(head -1 ${t}_$b | cut -d'|' -f1 | sed 's/.*: //')" "$(grep -E '^  3bet_opp ' ${t}_$b | sed 's/ *hands=/n=/;s/chips=.*(/(/')"; done; done
cat $1_d_*.txt | grep " vs " > /tmp/l3_$1.sum; cat $2_d_*.txt | grep " vs " > /tmp/l3_$2.sum
(cd ../.. && .venv/bin/python -m lab.eval --compare /tmp/l3_$1.sum /tmp/l3_$2.sum)
