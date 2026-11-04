"""PD numbers from logs/pd/runs/: two-part KEEP between two arms, single-arm lines, brain stats.

    .venv/bin/python logs/pd/analyze.py cmp ARM_A ARM_B BOT [BOT...]     # chips (locks off) + score (locks on)
    .venv/bin/python logs/pd/analyze.py line ARM LOCKS BOT [BOT...]      # the summary lines
    .venv/bin/python logs/pd/analyze.py stats ARM BOT [BOT...]           # hands200 member shares (locks off)
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lab.eval import LINE, compare as chips_compare  # noqa: E402
from lab.opps.score_compare import SCORE, compare as score_compare  # noqa: E402

RUNS = ROOT / "logs/pd/runs"
FAMILY = {"anti_folder": ["d_new_exploiter", "d_conv_opp3", "d_new_rules"],
          "anti_value": ["d_new_minraise", "d_new_trapper"], "anti_aggro": ["d_new_lag", "maniac"]}


def path(arm: str, bot: str, locks: str) -> Path:
    return RUNS / f"{arm}__{bot}__{locks}.txt"


def summary(arm: str, bot: str, locks: str) -> dict:
    line = next(l for l in path(arm, bot, locks).read_text().splitlines() if LINE.match(l))
    m, s = LINE.match(line), SCORE.search(line)
    return {"chips": float(m["m"]), "se": float(m["se"]), "score": float(s["s"]), "sse": float(s["se"]), "n": int(s["n"])}


def cmp(a: str, b: str, bots: list[str]) -> bool:
    ra = {x: summary(a, x, "off") for x in bots}
    rb = {x: summary(b, x, "off") for x in bots}
    lines, keep_c = chips_compare({x: (r["chips"], r["se"]) for x, r in ra.items()},
                                  {x: (r["chips"], r["se"]) for x, r in rb.items()})
    print(f"== chips (locks off) {a} -> {b}")
    print("\n".join(lines))
    sa, sb = ({x: (summary(arm, x, "on")["score"], summary(arm, x, "on")["sse"]) for x in bots} for arm in (a, b))
    lines, keep_s = score_compare(sa, sb)
    print(f"== match score (locks on) {a} -> {b}")
    print("\n".join(lines))
    print("TWO-PART:", "KEEP" if keep_c and keep_s else f"DROP (chips {keep_c}, score {keep_s})")
    return keep_c and keep_s


def fam_sum(a: str, b: str, bots: list[str], locks: str = "off") -> str:
    d = [summary(b, x, locks)["chips"] - summary(a, x, locks)["chips"] for x in bots]
    se = [math.hypot(summary(a, x, locks)["se"], summary(b, x, locks)["se"]) for x in bots]
    s, e = sum(d), math.sqrt(sum(v * v for v in se))
    return f"{s:+.2f} ± {e:.2f} (z {s / e:+.1f}), per bot " + ", ".join(f"{x} {v:+.2f}" for x, v in zip(bots, d))


def stats(arm: str, bots: list[str]) -> None:
    for bot in bots:
        txt = path(arm, bot, "off").read_text()
        for line in txt.splitlines():
            if line.startswith("--- brain stats") and "hands200_" in line:
                kv = dict(re.findall(r"(\w+)=(\d+)", line))
                h = {k[len("hands200_"):]: int(v) for k, v in kv.items() if k.startswith("hands200_")}
                tot = sum(h.values())
                print(f"{bot:18} hands>=200: " + " ".join(f"{k} {v / tot:.2f}" for k, v in h.items() if v) + f"  (n={tot})"
                      f"  switches {kv.get('sel_switches', 0)} bailouts {kv.get('sel_bailouts', 0)} stoploss {kv.get('sel_stoploss', 0)} errors {kv.get('p_errors', 0)}")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "cmp":
        raise SystemExit(0 if cmp(args[0], args[1], args[2:]) else 1)
    if cmd == "line":
        for bot in args[2:]:
            r = summary(args[0], bot, args[1])
            print(f"{args[0]} {bot} [{args[1]}]: {r['chips']:+.2f} ± {r['se']:.2f} chips/hand, score {r['score']:.3f} ± {r['sse']:.3f} ({r['n']} matches)")
    if cmd == "stats":
        stats(args[0], args[1:])
