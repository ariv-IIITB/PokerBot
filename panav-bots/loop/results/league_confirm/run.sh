set -x
cd /home/user/pokerbot
R=panav-bots/loop/results/league_confirm
for n in W1 W2 W3 W4; do
  PYTHONPATH=. .venv/bin/python panav-bots/loop/tools/file_duel.py panav-bots/loop/league/$n.py panav-bots/final/bot.py --seeds 24 --hands 200 --first-seed 2000 --processes 3 --logdir $R/logs_$n --out $R/${n}_24x200.json
done
for n in W1 W2 W3 W4; do
  PYTHONPATH=. .venv/bin/python panav-bots/loop/tools/file_duel.py panav-bots/loop/league/$n.py panav-bots/final/bot.py --seeds 8 --hands 500 --first-seed 2050 --processes 3 --out $R/${n}_8x500.json
done
echo ALLDONE
