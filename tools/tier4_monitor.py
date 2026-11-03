"""Tier 4 monitor (`python3 tools/tier4_monitor.py`, from the repo root): which sub-plans have handed off, on which branch, is the branch on the right base,
and which sub-plans are ready to start. Read-only on git (fetch only); prints JSON. Run from the repo root."""
import json, subprocess, sys
from pathlib import Path

STATE = Path(".scratch/tier4_state.json")   # {"started": [...]}: sub-plans already started (local, not committed)
# id -> (plan alias it should end up as, aliases that must be ancestors, prerequisites to start)
PLAN = {
    "S0": ("tier4/s0", ["tier4/base"], []),
    "PA": ("tier4/p", ["tier4/base"], []),
    "GX": ("tier4/gx", ["tier4/p"], ["PA"]),   # gate X redo on the laptop (sequential test)
    "PB": ("tier4/p-tune", ["tier4/p"], ["PA"]),
    "PC": ("tier4/p-sel", ["tier4/p"], ["PA"]),
    "PD": ("tier4/p", ["tier4/p-tune", "tier4/p-sel"], ["PB", "PC"]),
    "DA": ("tier4/d", ["tier4/base"], []),
    "DB": ("tier4/d-learn", ["tier4/base", "tier4/s0"], ["S0"]),
    "DC": ("tier4/d", ["tier4/d-learn"], ["DA", "DB"]),   # DA's branch checked via the alias
    "RA": ("tier4/r", ["tier4/base"], []),
    "RA2": ("tier4/r", ["tier4/r"], ["RA"]),
    "RB": ("tier4/r", ["tier4/r"], ["RA"]),
    "RC": ("tier4/r", ["tier4/r"], ["RB", "RA2"]),
    "I1": ("tier4/main", ["tier4/p", "tier4/d", "tier4/r"], ["PD", "DC", "RC"]),
}


def git(*a: str) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()


def is_anc(a: str, b: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b]).returncode == 0


def main() -> None:
    git("fetch", "-q", "--prune", "origin")
    state = json.loads(STATE.read_text()) if STATE.exists() else {"started": []}
    refs = [r for r in git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin").split() if "/" in r]
    found = {}   # id -> (branch, commit): the commit that last wrote docs/tier4/handoff/<id>.md, and the branch nearest it
    for ref in refs:
        if ref == "origin/tier4/base":
            continue
        for n in git("ls-tree", "--name-only", ref, "docs/tier4/handoff/").split():
            i = Path(n).stem
            if i not in PLAN:
                continue
            c = git("log", "-1", "--format=%H", ref, "--", n)
            ct = int(git("log", "-1", "--format=%ct", c))
            dist = int(git("rev-list", "--count", f"{c}..{ref}"))
            key = (ct, -dist)
            if i not in found or key > found[i][2]:
                found[i] = (ref, c, key)
    out = {"done": {}, "ready_to_start": [], "started_not_done": [], "problems": []}
    for i, (ref, c, _) in found.items():
        alias, ancestors, _ = PLAN[i]
        # tier4/base gets docs-only commits later; the code base is its exploit-layer merge
        req = ["a9fd1f3" if a == "tier4/base" else f"origin/{a}" for a in ancestors if a != alias]
        missing = [a for a in req if git("rev-parse", "-q", "--verify", a) and not is_anc(a, ref)]
        alias_ok = bool(git("rev-parse", "-q", "--verify", f"origin/{alias}")) and is_anc(c, f"origin/{alias}")
        out["done"][i] = {"branch": ref, "alias": alias, "alias_points_here_or_later": alias_ok, "missing_bases": missing}
        if missing:
            out["problems"].append(f"{i} on {ref} lacks {missing}")
    for i, (_, _, pre) in PLAN.items():
        if i in out["done"]:
            continue
        if i in state["started"]:
            out["started_not_done"].append(i)
        elif all(p in out["done"] for p in pre):
            out["ready_to_start"].append(i)
    json.dump(out, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
