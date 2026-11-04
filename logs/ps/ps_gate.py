"""PS driver: tier4p (auto) vs tier3x (both with O3's river rules), resumable, one file per run in logs/ps/runs/.

    nice -n 15 .venv/bin/python logs/ps/ps_gate.py
Seeds 74000-74999 (PS block); the same seeds for both arms. Laptop lock rules as in logs/pd/pd_gate.py.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "logs/ps/runs"
POOL = ["d_conv_opp3", "d_new_lag", "d_new_trapper", "d_new_exploiter", "d_new_minraise"]


def run(name: str, brain: str, opp: str, seed: int, locks: str, pairs: int = 50, stats: bool = False) -> None:
    f = RUNS / f"{name}__{opp}__{locks}.txt"
    if f.exists():
        return
    cmd = ['flock /tmp/pokerbot_turnstile.lock true; flock -s /tmp/pokerbot_laptop.lock "$@"', "_",
           str(ROOT / ".venv/bin/python"), "-m", "lab.eval", brain, "--pool", opp, "--pairs", str(pairs),
           "--first-seed", str(seed), "--locks", locks, "--variant", "discard_holdem", "--processes", "3",
           "--out", str(f)] + (["--report", "stats"] if stats else [])
    print("run", f.name, flush=True)
    with open("/tmp/ps_gate.err", "ab") as err:
        r = subprocess.run(["bash", "-c", *cmd], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=err)
    if r.returncode or not f.exists():
        f.unlink(missing_ok=True)
        raise SystemExit(f"lab.eval failed for {f.name} (rc {r.returncode})")


for locks in ("off", "on"):
    for opp in POOL:      # both arms back to back
        run("A_tier3x", "tier3x", opp, 74000, locks)
        run("B_tier4p", "tier4p", opp, 74000, locks, stats=(locks == "off"))
run("h2h_B_vs_A", "tier4p", "tier3x", 74500, "on")
print("done", flush=True)
