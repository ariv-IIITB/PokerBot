"""Queue: for each bot, base (with logs) + every switch build, 24 pairs x 200h, seeds 13000-13023, resumable.
usage: run_table.py PHASE   (PHASE base | sw)"""
import subprocess, sys, os, time
from pathlib import Path
R = Path("panav-bots/loop/results/meta1"); R.mkdir(parents=True, exist_ok=True)
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
SW = {s: f"panav-bots/loop/meta1/builds/sw_{s}.py" for s in ("foldall", "valuebet", "potfold", "probe")}
ORDER = sys.argv[2].split(",") if len(sys.argv) > 2 else list(BOTS)
def run(tag, bot, build, log=False):
    out = R / f"{tag}_{bot}.json"
    if out.exists(): return
    cmd = [".venv/bin/python", "panav-bots/loop/tools/file_duel.py", build, BOTS[bot], "--seeds", "24", "--first-seed", "13000",
           "--hands", "200", "--processes", "3", "--out", str(out)]
    if log: cmd += ["--logdir", str(R / "logs" / bot)]
    t = time.time()
    r = subprocess.run(cmd, env=dict(os.environ, PYTHONPATH="."), capture_output=True, text=True, timeout=3000)
    (R / f"{tag}_{bot}.txt").write_text(r.stdout + r.stderr)
    print(tag, bot, round(time.time() - t), r.stdout.splitlines()[0] if r.stdout else r.stderr[-200:], flush=True)
if sys.argv[1] == "base":
    for b in ORDER: run("base", b, BASE, log=True)
else:
    for b in ORDER:
        for s, p in SW.items(): run(s, b, p)
