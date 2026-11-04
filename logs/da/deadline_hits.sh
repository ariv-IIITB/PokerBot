#!/bin/bash
# "brain exceeded hard deadline" warnings per tuning point (all brains in the match, ours and the pool's), with the point's
# finish time. Decisions are not logged: ~4.5 of ours per hand x 192000 hands per point = ~864k, so per 1000 decisions = n/864.
cd "$(dirname "$0")/../.."
for f in $(ls -tr logs/da/cd_*.log); do
  n=$(grep -c 'exceeded hard deadline' $f)
  printf "%-45s %s  hits %4d  per1000dec %.2f\n" "$(basename $f .log)" "$(date -r $f +%d%H:%M)" $n $(python3 -c "print($n/864)")
done
