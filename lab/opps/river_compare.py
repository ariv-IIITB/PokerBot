"""Gate R, river buckets: compare the `river-all` accounting line of two `lab.eval --report accounting` files.

    .venv/bin/python -m lab.opps.river_compare BEFORE.txt AFTER.txt [opponent ...]

Per opponent: our river-all chips/hand before -> after, diff, SE (arms are independent runs, SEs add in quadrature),
z. `better` = z > 2. Exit 0 when every named opponent (default: all shared) is better."""
import math
import re
import sys
from pathlib import Path

from lab.eval import LINE

RIVER = re.compile(r"river-all .*\((?P<m>[+-][\d.]+) \+-(?P<se>[\d.]+)/hand")


def river_all(path: str) -> dict[str, tuple[float, float]]:
    out, opp, seen = {}, None, False
    for line in Path(path).read_text().splitlines():
        m = LINE.match(line)
        if m:
            opp, seen = m["b"].removesuffix("-nolock"), False
        elif line.startswith("--- accounting:"):
            seen = opp is not None and opp not in out and not seen     # the first block is ours
        elif seen and (m := RIVER.search(line)):
            out[opp] = (float(m["m"]), float(m["se"]))
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    a, b = river_all(argv[0]), river_all(argv[1])
    names = argv[2:] or [o for o in a if o in b]
    ok = bool(names)
    for o in names:
        (m0, s0), (m1, s1) = a[o], b[o]
        d, se = m1 - m0, math.hypot(s0, s1)
        z = d / se if se else 0.0
        ok = ok and z > 2
        print(f"{o:14} river-all {m0:+.3f} -> {m1:+.3f}  diff {d:+.3f} +- {se:.3f} (z {z:+.1f}) {'better' if z > 2 else 'not better by 2 SE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
