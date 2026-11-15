"""OPUS1: offline simulation of the probe-exit SPRT on hand logs (what the opponent SHOWS: its answer when it checked to
us on the TURN and we bet). Per leg: the hand at which the test decides "no" (exit), or never.
  .venv/bin/python panav-bots/loop/opus1/exit_sim.py LOGROOT_or_LOGDIR [p0 p1 alpha] """
import json, math, sys
from pathlib import Path

def legs(d):
    for f in sorted(d.glob("seed*_m*.jsonl")):
        obs = []
        for l in f.open():
            m = json.loads(l)
            if m["type"] != "hand_result": continue
            line = [e for e in m["history"] if e["street"] == "turn"]
            if len(line) >= 3 and line[0]["actor"] == "opp" and line[0]["action"] == "check" and line[1]["actor"] == "me" \
                    and line[1]["action"] == "raise":
                obs.append((m["hand_id"], line[2]["action"] == "fold"))
        yield f.name, obs

def sim(obs, p0, p1, a):
    lo, up = math.log(a / (1 - a)), math.log((1 - a) / a)
    sf, sn = math.log(p1 / p0), math.log((1 - p1) / (1 - p0))
    llr = 0.0
    for h, x in obs:
        llr += sf if x else sn
        if llr <= lo: return h
        if llr >= up: return None
    return None

root = Path(sys.argv[1]); p0, p1, a = (float(x) for x in (sys.argv[2:5] if len(sys.argv) > 4 else (0.28, 0.48, 0.10)))
dirs = [root] if list(root.glob("seed*.jsonl")) else sorted(x for x in root.iterdir() if x.is_dir())
for d in dirs:
    ex = []; n = 0; nobs = 0
    for name, obs in legs(d):
        n += 1; nobs += len(obs); e = sim(obs, p0, p1, a)
        if e is not None: ex.append(e)
    med = sorted(ex)[len(ex)//2] if ex else None
    print(f"{d.name:22s} legs {n:3d} turn obs/leg {nobs/max(1,n):5.1f} exits {len(ex):3d} ({100*len(ex)/max(1,n):3.0f}%) median exit hand {med}")
