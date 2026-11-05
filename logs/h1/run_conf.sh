#!/bin/bash
# H1 confirmation of D1: 100 pairs, fresh seeds 77400-77499, locks off (+stats), all 9 bots, base vs D1 back to back per bot.
cd "$(dirname "$0")/../.."
P=$(($(nproc)-1)); D=logs/h1/conf; C='tier3x:{"x_def":0.5,"x_def_margin":0.05}'
# (base = D1 off: D1 is the tier3x default since the H1 merge)
for opp in d_new_geometric d_conv_opp4 d_new_eqrandom d_conv_opp3 d_new_rules d_new_lag d_new_trapper d_new_exploiter d_new_minraise; do
  for a in base D1; do
    cfg='tier3x:{"x_def":0}'; [ $a = D1 ] && cfg="$C"
    out=$D/${a}_${opp}.txt; [ -s "$out" ] && continue
    .venv/bin/python -m lab.eval "$cfg" --pool $opp --final --pairs 100 --first-seed 77400 --locks off \
      --variant discard_holdem --processes $P --report stats --out $out > ${out%.txt}.log 2>&1
  done
done
echo done > $D/done
