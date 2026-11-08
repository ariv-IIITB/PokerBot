"""Summarise logs/combo/<locks>/<arm>__<bot>.txt (lab/combo_run.sh): each arm minus `base`, per bot and
summed (SE = hypot of the two arms' SEs per bot). Usage: python -m lab.combo_report [off|on] [DIR ...]"""
from __future__ import annotations

import math
import re
import sys
from collections import defaultdict
from pathlib import Path

LINE = re.compile(r"vs (\S+?)(?:-nolock)?: ([+-][\d.]+) ± ([\d.]+) chips/hand \| match score ([\d.]+) ± ([\d.]+)")


def load(dirs: list[Path]) -> dict:
    res: dict = defaultdict(dict)                 # arm -> bot -> (chips, se, score, sse)
    for d in dirs:
        for f in sorted(d.glob("*__*.txt")):
            arm, bot = f.stem.split("__", 1)
            m = LINE.search(f.read_text())
            if m:
                res[arm][bot] = tuple(float(x) for x in m.groups()[1:])
    return res


def main(argv: list[str]) -> None:
    locks = argv[0] if argv else "off"
    dirs = [Path(a) for a in argv[1:]] or [Path("logs/combo") / locks]
    res = load(dirs)
    base = res.get("base", {})
    bots = sorted(base)
    col = 3 if locks == "on" else 0             # locks on: compare match score; off: chips
    print(f"{'arm':10s} " + " ".join(f"{b[:12]:>13s}" for b in bots) + "      SUM ± SE   bots<-2SE")
    for arm in sorted(res, key=lambda a: (a != "base", a)):
        cells, tot, var, bad = [], 0.0, 0.0, 0
        for b in bots:
            if b not in res[arm]:
                cells.append(f"{'-':>13s}"); continue
            v, se = res[arm][b][col], res[arm][b][col + 1]
            if arm == "base":
                cells.append(f"{v:+13.2f}"); continue
            d, s = v - base[b][col], math.hypot(se, base[b][col + 1])
            tot, var = tot + d, var + s * s
            bad += int(d < -2 * s)
            cells.append(f"{d:+8.2f}±{s:4.2f}")
        tail = "" if arm == "base" else f"  {tot:+7.2f} ± {math.sqrt(var):.2f}   {bad}"
        print(f"{arm:10s} " + " ".join(cells) + tail)


if __name__ == "__main__":
    main(sys.argv[1:])
