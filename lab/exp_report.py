"""2-leg (whole match) score per arm vs a baseline arm, from logs/<dir>/<arm>__<bot>.txt (lab.eval output).

    .venv/bin/python -m lab.exp_report logs/lock [--base off]"""
from __future__ import annotations

import glob
import math
import os
import re
import sys
from collections import defaultdict

LINE = re.compile(r"([+-][\d.]+) ± ([\d.]+) chips/hand \| match score ([\d.]+) ± ([\d.]+) over \d+ matches \| "
                  r"2-leg score ([\d.]+) ± ([\d.]+)")


def main(argv: list[str]) -> None:
    d = argv[0] if argv else "logs/lock"
    base = argv[argv.index("--base") + 1] if "--base" in argv else "off"
    res: dict = defaultdict(dict)
    for f in glob.glob(os.path.join(d, "*__*.txt")):
        arm, bot = os.path.basename(f)[:-4].split("__", 1)
        m = LINE.search(open(f, errors="replace").read())
        if m:
            res[arm][bot] = tuple(map(float, m.groups()))
    if base not in res:
        print(f"no baseline arm {base!r}; arms: {sorted(res)}")
        return
    bots = sorted(res[base])
    print("arm".ljust(12) + "".join(b.replace("d_new_", "").replace("d_conv_", "")[:9].rjust(10) for b in bots)
          + "   mean 2-leg delta   chips delta")
    print(base.ljust(12) + "".join(f"{res[base][b][4]:.3f}".rjust(10) for b in bots))
    for arm in sorted(res):
        if arm == base:
            continue
        common = [b for b in bots if b in res[arm]]
        if not common:
            continue
        dl = [res[arm][b][4] - res[base][b][4] for b in common]
        se = math.sqrt(sum(res[arm][b][5] ** 2 + res[base][b][5] ** 2 for b in common)) / len(common)
        dc = [res[arm][b][0] - res[base][b][0] for b in common]
        cse = math.sqrt(sum(res[arm][b][1] ** 2 + res[base][b][1] ** 2 for b in common)) / len(common)
        cells = "".join((f"{res[arm][b][4] - res[base][b][4]:+.3f}" if b in res[arm] else "-").rjust(10) for b in bots)
        print(arm.ljust(12) + cells + f"   {sum(dl) / len(dl):+.3f} ± {se:.3f} ({len(common)})"
              + f"   {sum(dc) / len(dc):+.2f} ± {cse:.2f}")


if __name__ == "__main__":
    main(sys.argv[1:])
