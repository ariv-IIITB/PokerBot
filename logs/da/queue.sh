#!/bin/bash
# DA runs, strictly one after another (wall-clock budgets). Seeds 20000-20029, 30 pairs.
cd /home/user/PokerBot
while pgrep -f "lab.eval tier3 --pool train tier1 tier2 --pairs 30 --first-seed 20000 --locks off --variant discard_holdem --processes 3 --out logs/da/base_off" >/dev/null; do sleep 15; done
run() { # name locks config
  .venv/bin/python -m lab.eval "$3" --pool train tier1 tier2 --pairs 30 --first-seed 20000 --locks $2 --variant discard_holdem --processes 3 --out logs/da/$1.txt > logs/da/$1.log 2>&1
}
run a_off off 'tier3:{"smart_rollout_discard":true}'
run base_on on 'tier3'
run a_on on 'tier3:{"smart_rollout_discard":true}'
for s in m04 p00 p04; do for m in m02 p00 p02; do
  [ "$s$m" = "p00p00" ] && continue
  sh=$(python3 -c "print({'m04':-0.04,'p00':0,'p04':0.04}['$s'])"); mg=$(python3 -c "print(round(0.02+{'m02':-0.02,'p00':0,'p02':0.02}['$m'],2))")
  re=$(python3 -c "print([round(x+$sh,2) for x in [0.70,0.68,0.70,0.74]])")
  run g_${s}_${m}_off off "tier3:{\"smart_rollout_discard\":true,\"raise_equity\":$re,\"call_margin\":$mg}"
done; done
echo done > logs/da/queue.done
