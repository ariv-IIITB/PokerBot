#!/bin/bash
# PF step-1 probe: does the existing chart's btn-vs-3bet continue share matter? Both arms back to back.
cd "$(dirname "$0")/../.."
run() { # name config
  [ -s logs/pf/probe_$1.txt ] && return
  flock /tmp/pokerbot_turnstile.lock true
  nice -n 19 flock -s /tmp/pokerbot_laptop.lock nice -n 19 .venv/bin/python -m lab.eval "$2" \
    --pool d_conv_opp3,d_new_exploiter,d_new_lag --pairs 20 --first-seed 60000 --locks off \
    --variant discard_holdem --processes 1 --out logs/pf/probe_$1.txt > logs/pf/probe_$1.log 2>&1
}
run base 'tier3'
run c35 'tier3:{"pf_btn_continue":0.35}'
run c85 'tier3:{"pf_btn_continue":0.85,"pf_ratio_slope":0.0}'
