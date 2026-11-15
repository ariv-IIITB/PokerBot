#!/bin/bash
# every 28 min: partial summary + commit + push
cd /home/user/pokerbot
sleep 1680
pgrep -f probeval/run.py >/dev/null || echo "QUEUE DEAD"
.venv/bin/python panav-bots/loop/probeval/summ.py panav-bots/loop/reports/probeval_partial.md >/dev/null 2>&1
git add -A panav-bots/loop && git commit -qm "probeval: partial (MATCH WINS in reports/probeval_partial.md)" ; git push -q -u origin loop/probeval 2>&1 | tail -1
tail -2 panav-bots/loop/results/probeval/queue.log
