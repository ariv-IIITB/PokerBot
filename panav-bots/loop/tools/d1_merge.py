"""Concatenate row lists: d1_merge.py OUT.json IN.json [IN.json ...]"""
import json, sys
rows = []
for f in sys.argv[2:]:
    rows += json.load(open(f))
json.dump(rows, open(sys.argv[1], "w"))
print(len(rows), "rows")
