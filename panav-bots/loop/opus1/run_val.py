"""OPUS1 validation queue (resumable; pre-registered in reports/opus1_prereg.md).
v2 is always run (stderr kept); A is run on the same seeds only if v2's probe exit fired in >= 1 leg of that run.
  PYTHONPATH=. .venv/bin/python panav-bots/loop/opus1/run_val.py
"""
import os, re, subprocess, sys, time
from pathlib import Path

R = Path("panav-bots/loop/results/opus1/val"); R.mkdir(parents=True, exist_ok=True)
E, O = "panav-bots/eval_bots", "Opps/discard"
V2, A = "panav-bots/loop/cands/sub_v2.py", "panav-bots/loop/cands/sub_disc_probe.py"
OPP = {"new_trapper": f"{O}/new_trapper/bot.py", "trapper": f"{E}/spar/trapper/bot.py", "new_eqrandom": f"{O}/new_eqrandom/bot.py",
       "lakshya1": "panav-bots/opponents/lakshya1.py", "conv_opp3": f"{O}/conv_opp3/bot.py", "eqtag": f"{E}/spar/eqtag/bot.py",
       "potctl": f"{E}/spar/potctl/bot.py", "polar": f"{E}/spar/polar/bot.py", "new_geometric": f"{O}/new_geometric/bot.py",
       "new_exploiter": f"{O}/new_exploiter/bot.py",
       "new_lag": f"{O}/new_lag/bot.py", "new_minraise": f"{O}/new_minraise/bot.py", "new_rules": f"{O}/new_rules/bot.py",
       "conv_opp4": f"{O}/conv_opp4/bot.py", "s2_rollout": f"{E}/strong/s2_rollout/bot.py", "s5_preflop": f"{E}/strong/s5_preflop/bot.py",
       "s7_solver": f"{E}/strong/s7_solver/bot.py", "s10_regret": f"{E}/strong/s10_regret/bot.py", "light3b": f"{E}/spar/light3b/bot.py",
       "tilt": f"{E}/spar/tilt/bot.py"}
ORDER = ["new_trapper", "new_eqrandom", "lakshya1", "H2H", "trapper", "conv_opp3", "eqtag", "potctl", "polar", "new_geometric",
         "new_exploiter", "new_lag", "new_minraise", "new_rules", "conv_opp4", "s2_rollout", "s5_preflop", "s7_solver", "s10_regret",
         "light3b", "tilt", "S2:lakshya1", "S2:new_eqrandom"]


def duel(tag, a, b, first, seeds, hands, err):
    out = R / f"{tag}.json"
    if out.exists():
        return
    cmd = [sys.executable, "panav-bots/loop/opus1/duel.py", a, b, "--seeds", str(seeds), "--first-seed", str(first),
           "--hands", str(hands), "--processes", "3", "--out", str(out)]
    if err:
        cmd += ["--errdir", str(R / f"err_{tag}")]
    t = time.time()
    r = subprocess.run(cmd, env=dict(os.environ, PYTHONPATH="."), capture_output=True, text=True, timeout=4 * 3600)
    (R / f"{tag}.txt").write_text(r.stdout + r.stderr)
    print(tag, round(time.time() - t), (r.stdout.splitlines() or [r.stderr[-300:]])[0][:120], flush=True)


def fired(tag):
    """legs whose exploit summary shows the probe exit deciding 'no' at least once; and legs total."""
    d = R / f"err_{tag}"
    n = k = 0
    for f in sorted(d.glob("*.err")):
        txt = f.read_text(errors="replace")
        m = re.findall(r"'probeexit': \{[^}]*'events': \[([^\]]*)\]", txt)
        n += 1
        k += bool(m and "'no'" in m[-1])
    return k, n


for name in ORDER:
    if name == "H2H":
        duel("h2h_v2_A", V2, A, 52000, 40, 200, True)
        continue
    if name.startswith("S2:"):
        o = name[3:]
        tag, first, seeds, hands = f"S2_{o}", 51000, 24, 500
    else:
        o, tag, first, seeds, hands = name, f"S1_{name}", 50000, 40, 200
    duel(f"v2_{tag}", V2, OPP[o], first, seeds, hands, True)
    k, n = fired(f"v2_{tag}")
    (R / f"v2_{tag}.fired").write_text(f"{k} {n}\n")
    print(f"  {tag}: exit fired in {k}/{n} legs", flush=True)
    if k > 0:
        duel(f"A_{tag}", A, OPP[o], first, seeds, hands, False)
print("DONE", flush=True)
