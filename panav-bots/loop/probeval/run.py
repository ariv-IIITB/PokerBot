"""Resumable queue for PROBEVAL. usage: run.py (runs everything; skips existing outputs)."""
import subprocess, sys, os, time
from pathlib import Path
R = Path("panav-bots/loop/results/probeval"); R.mkdir(parents=True, exist_ok=True)
E = "panav-bots/eval_bots"
BOTS = {}
for n in "eqtag polar trapper potctl betfold light3b tilt donk adapt discardread".split():
    BOTS[n] = f"{E}/spar/{n}/bot.py"
for n in "s1_ranges s5_preflop s2_rollout s6_discard s3_exploit s7_solver s9_sizing s4_balanced s8_meta s10_regret".split():
    BOTS[n] = f"{E}/strong/{n}/bot.py"
for n in "new_lag conv_opp3 new_trapper conv_opp4 new_minraise new_rules new_geometric new_exploiter new_eqrandom".split():
    BOTS[n] = f"Opps/discard/{n}/bot.py"
BOTS["lakshya1"] = "panav-bots/opponents/lakshya1.py"
BASE = "panav-bots/loop/evalbuilds/final_seeded.py"
CAND = "panav-bots/loop/meta1/builds/sw_probe.py"
def run(tag, bot, A, B, first, seeds, hands):
    out = R / f"{tag}.json"
    if out.exists(): return
    cmd = [".venv/bin/python", "panav-bots/loop/tools/file_duel.py", A, B, "--seeds", str(seeds), "--first-seed", str(first),
           "--hands", str(hands), "--processes", "3", "--out", str(out)]
    t = time.time()
    r = subprocess.run(cmd, env=dict(os.environ, PYTHONPATH="."), capture_output=True, text=True, timeout=7200)
    (R / f"{tag}.txt").write_text(r.stdout + r.stderr)
    print(tag, round(time.time() - t), (r.stdout.splitlines() or [r.stderr[-200:]])[0][:110], flush=True)
jobs = []
for b in BOTS:                       # Stage 1
    for t, p in (("base", BASE), ("probe", CAND)):
        jobs.append((f"s1_{t}_{b}", b, p, BOTS[b], 30000, 40, 200))
for b in ("lakshya1", "new_eqrandom"):   # Stage 2
    for t, p in (("base", BASE), ("probe", CAND)):
        jobs.append((f"s2_{t}_{b}", b, p, BOTS[b], 30100, 24, 500))
jobs.append(("h2h_200", "-", CAND, BASE, 30200, 40, 200))
order = sys.argv[1:] 
if order: jobs = [j for j in jobs if any(j[0].endswith(o) or o in j[0] for o in order)]
for j in jobs: run(j[0], j[1], j[2], j[3], j[4], j[5], j[6])
print("DONE", flush=True)
