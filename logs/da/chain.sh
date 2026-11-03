#!/bin/bash
cd "$(dirname "$0")/../.."
while pgrep -f "[d]a/driver.py cd|[d]a/driver.py$" >/dev/null; do sleep 60; done
[ -f logs/da/best.json ] || { echo "descent did not finish"; exit 1; }
nice -n 15 .venv/bin/python logs/da/driver.py grid && nice -n 15 .venv/bin/python logs/da/driver.py confirm
