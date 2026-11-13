cd /home/user/pokerbot
R=panav-bots/loop/results/league_confirm
while ! grep -q ALLDONE $R/confirm500.log; do sleep 5; done
D="panav-bots/eval_bots"
for b in $D/spar/eqtag/bot.py $D/strong/s1_ranges/bot.py Opps/discard/new_lag/bot.py Opps/discard/conv_opp3/bot.py panav-bots/opponents/lakshya1.py; do
  PYTHONPATH=. .venv/bin/python panav-bots/loop/tools/file_duel.py panav-bots/loop/league/W1.py $b --seeds 8 --hands 200 --first-seed 2060 --processes 3
done
PYTHONPATH=. .venv/bin/python panav-bots/loop/tools/file_duel.py panav-bots/final/bot.py panav-bots/opponents/lakshya1.py --seeds 8 --hands 200 --first-seed 2060 --processes 3 --logdir $R/logs_final_vs_lk
PYTHONPATH=. .venv/bin/python panav-bots/loop/tools/file_duel.py panav-bots/final/bot.py panav-bots/loop/league/W1.py --seeds 8 --hands 200 --first-seed 2060 --processes 3 --logdir $R/logs_final_vs_W1
echo ZOODONE
