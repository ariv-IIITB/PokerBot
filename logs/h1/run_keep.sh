#!/bin/bash
# H1 KEEP for one candidate vs base (= tier4/int tier3x): 50 pairs, seeds 77300-77349, all 9 bots, locks off (+stats) then on;
# guard 20 pairs locks on (seeds 77800+); timing tier3 vs base vs candidate. Usage: run_keep.sh NAME 'tier3x:{...}'
cd "$(dirname "$0")/../.."
P=$(($(nproc)-1)); N=$1; C=$2; D=logs/h1/keep
while pgrep -f run_scr.sh >/dev/null; do sleep 30; done
pkill -f run_base.sh; sleep 2; pkill -f "first-seed 77000 --locks on"
BOTS="d_new_geometric d_conv_opp4 d_new_eqrandom d_conv_opp3 d_new_rules d_new_lag d_new_trapper d_new_exploiter d_new_minraise"
for l in off on; do
  for opp in $BOTS; do
    for a in base $N; do
      cfg=tier3x; [ $a = $N ] && cfg="$C"
      out=$D/${a}_${l}_${opp}.txt; [ -s "$out" ] && continue
      rep=""; [ $l = off ] && rep="--report stats"
      .venv/bin/python -m lab.eval "$cfg" --pool $opp --final --pairs 50 --first-seed 77300 --locks $l \
        --variant discard_holdem --processes $P $rep --out $out > ${out%.txt}.log 2>&1
    done
  done
done
out=$D/${N}_guard.txt
[ -s "$out" ] || .venv/bin/python -m lab.eval "$C" --pool calling_station starter tight maniac random_legal all_in --pairs 20 \
  --first-seed 77800 --locks on --variant discard_holdem --processes $P --out $out > ${out%.txt}.log 2>&1
out=$D/${N}_timing.txt
if [ ! -s "$out" ]; then
  for h in 400 1000; do for opp in d_new_geometric d_new_trapper; do for b in tier3 tier3x "$C"; do
    echo "=== $b vs $opp $h hands"; .venv/bin/python -m lab.timing_bench --brain "$b" --opponent $opp --variant discard_holdem --hands $h --seed 1 2>&1 | tail -12
  done; done; done > $out.tmp && mv $out.tmp $out
fi
echo done > $D/${N}.done
nohup logs/h1/run_base.sh > logs/h1/run_base.out 2>&1 &
