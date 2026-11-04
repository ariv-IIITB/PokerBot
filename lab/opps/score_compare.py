"""Compare mean match scores of two lab.eval result files (the second half of a two-part KEEP).

    .venv/bin/python -m lab.opps.score_compare BEFORE.txt AFTER.txt

Both files are `lab.eval --out` outputs from locks-ON runs. Per opponent: the mean match score
(win 1, draw 0.5, loss 0) before and after, the difference and its SE. Overall: the unweighted
mean over the opponents both files share. Verdict: DROP-score if the overall mean is lower by
more than 2 SE, else KEEP-score. Exit code 0 = KEEP-score, 1 = DROP-score.

SE comes from the summary lines ("match score 0.480 ± 0.050 over 100 matches"), which are the
SE over individual matches; the two files are independent runs, so SEs add in quadrature.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Optional

from lab.eval import LINE   # "<a> vs <b>: +x ± se chips/hand", the same line lab.eval --compare parses

SCORE = re.compile(r"match score (?P<s>[\d.]+) ± (?P<se>[\d.]+) over (?P<n>\d+) matches")


def parse_scores(path: str | Path) -> dict[str, tuple[float, float]]:
    """opponent -> (mean match score, SE) from the summary lines of a lab.eval output file."""
    out = {}
    for line in Path(path).read_text().splitlines():
        m, s = LINE.match(line), SCORE.search(line)
        if m and s:
            out[m["b"].removesuffix("-nolock")] = (float(s["s"]), float(s["se"]))
    return out


def compare(before: dict, after: dict) -> tuple[list[str], bool]:
    """(report lines, keep?) for two parsed score sets."""
    shared = [o for o in before if o in after]
    if not shared:
        return ["no opponents in common"], False
    lines = []
    for o in shared:
        (m0, s0), (m1, s1) = before[o], after[o]
        d, se = m1 - m0, math.hypot(s0, s1)
        lines.append(f"{o:16} {m0:.3f} -> {m1:.3f}  diff {d:+.3f} ± {se:.3f}")
    n = len(shared)
    m0 = sum(before[o][0] for o in shared) / n
    m1 = sum(after[o][0] for o in shared) / n
    se = math.sqrt(sum(before[o][1] ** 2 + after[o][1] ** 2 for o in shared)) / n
    d = m1 - m0
    z = d / se if se else 0.0
    keep = not (d < -2 * se)
    lines.append(f"{'overall':16} {m0:.3f} -> {m1:.3f}  diff {d:+.3f} ± {se:.3f} (z {z:+.1f}, {n} bots)")
    lines.append("verdict: " + ("KEEP-score" if keep else "DROP-score"))
    return lines, keep


def main(argv: Optional[list[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__)
        return 2
    lines, keep = compare(parse_scores(args[0]), parse_scores(args[1]))
    print("\n".join(lines))
    return 0 if keep else 1


if __name__ == "__main__":
    raise SystemExit(main())
