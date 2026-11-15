"""INT2 queue (resumable). A=sub_disc_probe, F=final, C=probe-only, B=disc-only; all normal (non-seeded) builds."""
import subprocess, os, time
from pathlib import Path
R = Path("panav-bots/loop/results/int2"); R.mkdir(parents=True, exist_ok=True)
E = "panav-bots/eval_bots"; C = "panav-bots/loop/cands"
BOT = {"A": f"{C}/sub_disc_probe.py", "F": "panav-bots/final/bot.py", "C": f"{C}/sub_probe_only.py", "B": f"{C}/sub_disc_only.py"}
OPP = {"lakshya1": "panav-bots/opponents/lakshya1.py", "new_trapper": "Opps/discard/new_trapper/bot.py",
       "conv_opp3": "Opps/discard/conv_opp3/bot.py", "new_eqrandom": "Opps/discard/new_eqrandom/bot.py",
       "eqtag": f"{E}/spar/eqtag/bot.py", "potctl": f"{E}/spar/potctl/bot.py", "polar": f"{E}/spar/polar/bot.py"}
def run(tag, a, b, first, seeds, hands):
    out = R / f"{tag}.json"
    if out.exists(): return
    cmd = [".venv/bin/python", "panav-bots/loop/tools/file_duel.py", a, b, "--seeds", str(seeds), "--first-seed", str(first),
           "--hands", str(hands), "--processes", "3", "--out", str(out)]
    t = time.time()
    r = subprocess.run(cmd, env=dict(os.environ, PYTHONPATH="."), capture_output=True, text=True)
    (R / f"{tag}.txt").write_text(r.stdout + r.stderr)
    print(tag, round(time.time() - t), (r.stdout.splitlines() or [r.stderr[-200:]])[0][:110], flush=True)
jobs = [("h2h_A_F", "A", "F", 40000, 40, 200)]
for o in OPP: jobs.append((f"A_{o}", "A", o, 41000, 24, 200))
for o in OPP: jobs.append((f"F_{o}", "F", o, 41000, 24, 200))
jobs.append(("h2h_A_C", "A", "C", 40100, 24, 200))
for o in OPP: jobs.append((f"C_{o}", "C", o, 41000, 24, 200))
for o in OPP: jobs.append((f"B_{o}", "B", o, 41000, 24, 200))
for tag, a, b, f, s, h in jobs:
    run(tag, BOT.get(a, a) if a in BOT else a, OPP.get(b, BOT.get(b, b)), f, s, h)
print("DONE", flush=True)
