"""PD (laptop) gate P driver: a resumable queue of lab.eval runs, one file per run in logs/pd/runs/.

    nice -n 15 .venv/bin/python logs/pd/pd_gate.py PHASE     # PHASE = step0 | gate
An existing run file is never re-run. Both arms of a comparison are queued back to back.
Seeds 12000-12999 (PD block). Light testing (user, 2026-11-03): 50 pairs, no sequential extension.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "logs/pd/runs"
PROCS = 3
PAIRS = 50
TRAIN = ["d_conv_opp3", "d_new_rules", "d_new_lag", "d_new_trapper", "d_new_exploiter", "d_new_minraise"]
FAMILY = {"anti_folder": ["d_new_exploiter", "d_conv_opp3", "d_new_rules"],
          "anti_value": ["d_new_minraise", "d_new_trapper"], "anti_aggro": ["d_new_lag", "maniac"]}


def forced(member: str, pt: dict | None = None) -> str:
    cfg = {"member": member}
    if pt:
        cfg["members"] = {member: pt}
    return "tier4p:" + json.dumps(cfg, sort_keys=True, separators=(",", ":"))


PA_DEFAULTS = {"anti_value": {"av_raise_fold_eq": 0.6}, "anti_aggro": {"aa_mdf_mult": 1.1, "aa_bluff_mult": 0.5}}


def run(name: str, brain: str, opp: str, seed: int, locks: str, pairs: int = PAIRS, stats: bool = False) -> None:
    f = RUNS / f"{name}__{opp}__{locks}.txt"
    if f.exists():
        return
    cmd = ['flock /tmp/pokerbot_turnstile.lock true; flock -s /tmp/pokerbot_laptop.lock "$@"', "_",
           str(ROOT / ".venv/bin/python"), "-m", "lab.eval", brain, "--pool", opp, "--pairs", str(pairs),
           "--first-seed", str(seed), "--locks", locks, "--variant", "discard_holdem", "--processes", str(PROCS),
           "--out", str(f)] + (["--report", "stats"] if stats else [])
    print("run", f.name, flush=True)
    with open("/tmp/pd_gate.err", "ab") as err:
        r = subprocess.run(["bash", "-c", *cmd], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=err)
    if r.returncode or not f.exists():
        f.unlink(missing_ok=True)
        raise SystemExit(f"lab.eval failed for {f.name} (rc {r.returncode})")


def step0() -> None:
    for seed, member in ((12000, "anti_value"), (12100, "anti_aggro")):
        for locks in ("off", "on"):
            for opp in FAMILY[member]:
                run(f"s0_{member}_pa", forced(member, PA_DEFAULTS[member]), opp, seed, locks)
                run(f"s0_{member}_pb", forced(member), opp, seed, locks)


def gate() -> None:
    # item 2: each forced member vs tier3 head to head
    for member in FAMILY:
        for locks in ("off", "on"):
            run(f"i2_{member}", forced(member), "tier3", 12200, locks)
    # item 3 head to head: auto tier4p vs the incumbent tier3x
    for locks in ("off", "on"):
        run("i3h2h_tier4p", "tier4p", "tier3x", 12300, locks)
    # items 3, 4 and the extra: training pool, same seeds for every arm
    for locks in ("off", "on"):
        for opp in TRAIN:
            run("pool_tier4p", "tier4p", opp, 12400, locks, stats=(locks == "off"))
            run("pool_tier3x", "tier3x", opp, 12400, locks)
    for opp in TRAIN:       # extra: forced anti_folder on the whole pool, locks off
        run("pool_forced_anti_folder", forced("anti_folder"), opp, 12400, "off")
    # item 5: adversary
    for opp in ("adversary", "adversary_strict"):
        run("i5_tier4p", "tier4p", opp, 12600, "off", stats=True)
        run("i5_tier3x", "tier3x", opp, 12600, "off")


def extra() -> None:
    # item 3's anti_aggro family needs maniac (not in the training pool); same seeds for both arms
    for locks in ("off", "on"):
        run("pool_tier4p", "tier4p", "maniac", 12400, locks, stats=(locks == "off"))
        run("pool_tier3x", "tier3x", "maniac", 12400, locks)
    # information only: item 2's anti_value score on fresh seeds
    for locks in ("off", "on"):
        run("i2b_anti_value", forced("anti_value"), "tier3", 12250, locks)


if __name__ == "__main__":
    {"step0": step0, "gate": gate, "extra": extra}[sys.argv[1]]()
    print("done", sys.argv[1], flush=True)
