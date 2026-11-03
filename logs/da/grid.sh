#!/bin/bash
# DA grid (resumable: skips points that already have a .txt). 30 pairs, seeds 20000-20029, locks off.
cd /home/user/PokerBot
for s in m04 p00 p04; do for m in m02 p00 p02; do
  [ "$s$m" = "p00p00" ] && continue
  n=g_${s}_${m}_off; [ -s logs/da/$n.txt ] && continue
  sh=$(python3 -c "print({'m04':-0.04,'p00':0,'p04':0.04}['$s'])"); mg=$(python3 -c "print(round(0.02+{'m02':-0.02,'p00':0,'p02':0.02}['$m'],2))")
  re=$(python3 -c "print([round(x+$sh,2) for x in [0.70,0.68,0.70,0.74]])")
  .venv/bin/python -m lab.eval "tier3:{\"smart_rollout_discard\":true,\"raise_equity\":$re,\"call_margin\":$mg}" --pool train tier1 tier2 --pairs 30 --first-seed 20000 --locks off --variant discard_holdem --processes 3 --out logs/da/$n.txt > logs/da/$n.log 2>&1
done; done
echo done > logs/da/grid.done
