#!/usr/bin/env bash
# V1 job runner (sequential, skips finished outputs). Run from repo root.
W=${W:-/tmp/claude-0/-home-user-pokerbot/82089a8f-a1c5-57b2-a466-f845827faebe/scratchpad}
R=panav-bots/loop; O=$R/results/v1; mkdir -p $O
B=$W/base_seeded.py; C=$W/cand_seeded.py
duel(){ # name A B seeds hands first out
  [ -f $O/$7.json ] && return
  PYTHONPATH=. timeout 900 .venv/bin/python $R/tools/v1_duel.py $2 $3 --seeds $4 --hands $5 --first-seed $6 --processes 3 --out $O/$7.json > $O/$7.txt 2>&1
}
bots="spar/trapper spar/potctl spar/polar spar/betfold spar/light3b spar/donk spar/adapt spar/tilt spar/discardread"
for b in $bots; do n=${b#*/}; p=panav-bots/eval_bots/$b/bot.py
  duel x $B $p 24 200 5000 base_$n; duel x $C $p 24 200 5000 cand_$n; done
for n in new_rules new_geometric new_exploiter new_eqrandom new_trapper conv_opp3 conv_opp4 new_lag new_minraise; do p=Opps/discard/$n/bot.py
  duel x $B $p 24 200 5000 base_$n; duel x $C $p 24 200 5000 cand_$n; done
L=panav-bots/opponents/lakshya1.py
duel x $B $L 24 500 5100 base_lakshya; duel x $C $L 24 500 5100 cand_lakshya
duel x $C $B 24 200 5000 h2h
[ -f $W/adv_done ] || true
for n in s4_balanced s5_preflop s6_discard s7_solver s8_meta s9_sizing s10_regret; do p=panav-bots/eval_bots/strong/$n/bot.py
  duel x $B $p 24 200 5000 base_$n; duel x $C $p 24 200 5000 cand_$n; done
echo ALLDONE > $O/ALLDONE
