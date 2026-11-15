"""Smoke matches for the sparring bots on the official engine.

    python eval/bots/spar/smoke.py [--workers 2] [bot ...]

Each bot plays one Stage 1 and one Stage 2 match against eqtag and against itself (eqtag against itself once).
A run passes with 0 forfeits and 0 notices (a notice means the bot sent an illegal or malformed reply, so stdout
carried something other than a clean protocol reply) and an empty stderr (no debug noise).
"""
import argparse
import concurrent.futures as cf
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ENGINE = ROOT / "starter_kit" / "engine.py"
PY = ROOT / ".venv311" / "bin" / "python"
NAMES = ["eqtag", "trapper", "potctl", "polar", "betfold", "light3b", "donk", "adapt", "tilt", "discardread"]


def one(a, b, stage, seed):
    with tempfile.TemporaryDirectory() as d:
        cmd = [str(PY), str(ENGINE), str(HERE / a / "main_bot.py"), str(HERE / b / "main_bot.py"), "--stage", str(stage),
               "--seed", seed, "--log-dir", d, "--python", str(PY)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        out = r.stdout + r.stderr
        stderr_bytes = sum(p.stat().st_size for p in pathlib.Path(d).glob("*_stderr.txt"))
    forfeit = "forfeited" in out
    notices = [int(x) for x in re.findall(r"notices (\d+)", out)]
    res = re.search(r"Result: (.*)", out)
    ok = r.returncode == 0 and not forfeit and sum(notices) == 0 and stderr_bytes == 0
    return ok, f"{a} vs {b} stage {stage}: {'PASS' if ok else 'FAIL'}  notices {notices}  stderr {stderr_bytes} B  " \
                f"{res.group(1) if res else out[-200:]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bots", nargs="*", default=NAMES)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    jobs = []
    for n in args.bots:
        for stage in (1, 2):
            jobs.append((n, "eqtag", stage, f"smoke-{n}-{stage}-a"))
            if n != "eqtag":
                jobs.append((n, n, stage, f"smoke-{n}-{stage}-b"))
    bad = 0
    with cf.ThreadPoolExecutor(args.workers) as ex:
        for ok, line in ex.map(lambda j: one(*j), jobs):
            print(line, flush=True)
            bad += not ok
    print("ALL PASS" if not bad else f"{bad} FAILED")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
