"""PB grid driver: one lab.eval run per grid point, resumable (skips points whose output exists).

    .venv/bin/python logs/pb/grid.py run MEMBER          # the grid (16 pairs, locks off)
    .venv/bin/python logs/pb/grid.py table MEMBER        # ranked table (sum of chips/hand over the family)
"""
import itertools, json, math, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lab.eval import parse_summary  # noqa: E402

# One-at-a-time design (user decision): the default point plus each parameter at its other grid values,
# the rest at their defaults. Interactions between parameters are NOT tested.
GRIDS = {   # from docs/tier4/handoff/PA.md
    "anti_folder": {"x_bluff_max": [0.45, 0.60, 0.75], "x_river_bluff_mult": [1.5, 2.5, 3.5],
                    "x_vo_margin": [0.06, 0.12, 0.18]},
    "anti_value": {"x_vo_margin": [0.06, 0.12, 0.18], "av_raise_fold_eq": [0.45, 0.65]},   # default 0.60 is off the PA grid: the two extremes
    "anti_aggro": {"aa_call_margin": [-0.06, -0.03, 0.0], "aa_mdf_mult": [1.0, 1.1, 1.2],
                   "aa_bluff_mult": [0.25, 0.50, 0.75]},
}
START = {"anti_folder": {"x_bluff_max": 0.60, "x_river_bluff_mult": 2.5, "x_vo_margin": 0.12},
         "anti_value": {"x_vo_margin": 0.12, "av_raise_fold_eq": 0.60},
         "anti_aggro": {"aa_call_margin": -0.03, "aa_mdf_mult": 1.10, "aa_bluff_mult": 0.50}}
FAMILY = {"anti_folder": "d_new_exploiter,d_conv_opp3,d_new_rules",
          "anti_value": "d_new_minraise,d_new_trapper", "anti_aggro": "d_new_lag,maniac"}
SEED = {"anti_folder": 10000, "anti_value": 10100, "anti_aggro": 10200}
PAIRS, PROCS = 16, 3


def tag(pt: dict) -> str:
    return "_".join(f"{v:g}" for v in pt.values())


def points(member: str) -> list[dict]:
    """Default point first, then one parameter moved at a time to each of its other grid values."""
    pts = [dict(START[member])]
    for k, vals in GRIDS[member].items():
        for v in vals:
            if v != START[member][k]:
                pts.append({**START[member], k: v})
    return pts


def brain(member: str, pt: dict) -> str:
    return "tier4p:" + json.dumps({"member": member, "members": {member: pt}}, separators=(",", ":"))


def run(member: str) -> None:
    d = ROOT / "logs" / "pb" / member
    d.mkdir(parents=True, exist_ok=True)
    for pt in points(member):
        out = d / f"{tag(pt)}.txt"
        if out.exists():
            continue
        tmp = out.with_suffix(".part")
        cmd = [sys.executable, "-m", "lab.eval", brain(member, pt), "--pool", FAMILY[member],
               "--pairs", str(PAIRS), "--first-seed", str(SEED[member]), "--locks", "off",
               "--variant", "discard_holdem", "--processes", str(PROCS), "--out", str(tmp)]
        print("RUN", member, pt, flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
        tmp.rename(out)


def table(member: str, d: Path | None = None) -> list[tuple]:
    d = d or ROOT / "logs" / "pb" / member
    rows = []
    for pt in points(member):
        f = d / f"{tag(pt)}.txt"
        if not f.exists():
            continue
        r = parse_summary(f)
        s = sum(m for m, _ in r.values())
        se = math.sqrt(sum(e * e for _, e in r.values()))
        rows.append((s, se, pt, r))
    rows.sort(key=lambda x: -x[0])
    keys = list(GRIDS[member])
    opps = list(rows[0][3]) if rows else []
    print("| " + " | ".join(keys + opps + ["sum"]) + " |")
    print("|" + "---|" * (len(keys) + len(opps) + 1))
    for s, se, pt, r in rows:
        mark = " (start)" if pt == START[member] else ""
        cells = [f"{pt[k]:g}" for k in keys] + [f"{r[o][0]:+.2f} ± {r[o][1]:.2f}" for o in opps]
        print("| " + " | ".join(cells) + f" | **{s:+.2f} ± {se:.2f}**{mark} |")
    return rows


if __name__ == "__main__":
    {"run": run, "table": table}[sys.argv[1]](sys.argv[2])
