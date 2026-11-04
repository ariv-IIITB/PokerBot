cd "$(dirname "$0")/../.."
until [ -f logs/o3c/s3_B_off.json ] && grep -q TIMING_DONE logs/o3c/timing.txt 2>/dev/null; do sleep 180; done
.venv/bin/python -m lab.eval --compare logs/o3c/s3_base_off.json logs/o3c/s3_A_off.json | tail -8
.venv/bin/python -m lab.eval --compare logs/o3c/s3_base_off.json logs/o3c/s3_B_off.json | tail -8
.venv/bin/python -m lab.eval --compare logs/o3c/s3_A_off.json logs/o3c/s3_B_off.json | tail -8
cat logs/o3c/timing.txt
