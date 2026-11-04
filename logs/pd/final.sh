#!/bin/bash
cd "$(dirname "$0")/../.."
echo "== slow tier4p timing tests"; .venv/bin/python -m pytest tests/test_timing_slow.py -m slow -k tier4p -q -p no:xdist 2>&1 | tail -6
echo "== memory"; .venv/bin/python -m lab.memory_check --variant discard_holdem 2>&1 | tail -6
