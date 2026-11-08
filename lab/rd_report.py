"""RD: per-bot table of arms against a base arm from logs/rd/ab.sh outputs.

    .venv/bin/python -m lab.rd_report DIR[,DIR...] BASE ARM [ARM...] [--bots a,b,c]

Each DIR holds chips_<arm>_<bot>.txt (lab.eval --report accounting, locks off). Prints, per bot, the arm's chips/hand
and the river-all line, and the difference to BASE (SEs in quadrature, arms are independent runs on the same seeds)."""
import math
import re
import sys
from pathlib import Path

from lab.eval import LINE
from lab.opps.river_compare import RIVER


def read(dirs, arm, bot):
    for d in dirs:
        f = Path(d) / f"chips_{arm}_{bot}.txt"
        if f.exists() and f.stat().st_size:
            txt = f.read_text()
            m = re.search(r"([+-][\d.]+) ± ([\d.]+) chips/hand \| match score ([\d.]+)", txt)
            r = RIVER.search(txt)
            return (float(m[1]), float(m[2]), float(m[3])), ((float(r["m"]), float(r["se"])) if r else None)
    return None, None


def main(argv):
    bots = None
    if "--bots" in argv:
        i = argv.index("--bots")
        bots = argv[i + 1].split(",")
        argv = argv[:i] + argv[i + 2:]
    dirs, base, arms = argv[0].split(","), argv[1], argv[2:]
    bots = bots or sorted({re.match(r"chips_\w+?_(d_\w+)\.txt", f.name)[1] for d in dirs for f in Path(d).glob("chips_*.txt")
                           if re.match(r"chips_\w+?_(d_\w+)\.txt", f.name)})
    tot = {a: [0.0, 0.0] for a in arms}
    for b in bots:
        c0, r0 = read(dirs, base, b)
        if not c0:
            continue
        print(f"== {b}: {base} chips {c0[0]:+.2f} ± {c0[1]:.2f} score {c0[2]:.3f}; river-all {r0[0]:+.3f} ± {r0[1]:.3f}" if r0 else f"== {b}")
        for a in arms:
            c, r = read(dirs, a, b)
            if not c:
                continue
            d, se = c[0] - c0[0], math.hypot(c[1], c0[1])
            tot[a][0] += d
            tot[a][1] += se * se
            rv = f"river-all {r[0]:+.3f} (diff {r[0] - r0[0]:+.3f} ± {math.hypot(r[1], r0[1]):.3f})" if r and r0 else ""
            print(f"   {a:4} chips {c[0]:+.2f} ± {c[1]:.2f}  vs base {d:+.2f} ± {se:.2f} (z {d / se:+.1f})  score {c[2]:.3f}  {rv}")
    for a in arms:
        print(f"sum over bots {a}: {tot[a][0]:+.2f} ± {math.sqrt(tot[a][1]):.2f}")


if __name__ == "__main__":
    main(sys.argv[1:])
