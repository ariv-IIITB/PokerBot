"""Fresh-seed replication (seeds 14000-14023) of base vs forced probe on the F4 fold + new_trapper."""
import subprocess, os, sys, time
sys.argv = [sys.argv[0], "x"]
exec(open("panav-bots/loop/meta1/run_table.py").read().split("def run(")[0])
R2 = R / "rep"; R2.mkdir(exist_ok=True)
for b in "new_trapper donk adapt discardread s4_balanced s8_meta s10_regret new_exploiter new_eqrandom".split():
    for tag, build in (("base", BASE), ("probe", SW["probe"])):
        out = R2 / f"{tag}_{b}.json"
        if out.exists(): continue
        cmd = [".venv/bin/python", "panav-bots/loop/tools/file_duel.py", build, BOTS[b], "--seeds", "24", "--first-seed", "14000",
               "--hands", "200", "--processes", "3", "--out", str(out)]
        r = subprocess.run(cmd, env=dict(os.environ, PYTHONPATH="."), capture_output=True, text=True, timeout=3000)
        print(tag, b, r.stdout.splitlines()[0][:90] if r.stdout else r.stderr[-200:], flush=True)
