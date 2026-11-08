"""What is more thinking time worth? tier3x as if on a K-times faster machine (its replies are charged 1/K, the
river solver's wall-clock box is K times larger) vs the same bot at normal speed, each against the same opponent on
the same duplicate deals. If K=4 adds nothing, faster code (lookup tables, a faster evaluator) adds nothing either.

    .venv/bin/python -m lab.compute_value --opponents d_new_exploiter,d_conv_opp3 --pairs 30 --speeds 1,4"""
from __future__ import annotations

import argparse
import math
from multiprocessing import Pool

from bot.timing import TimingConfig
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec


def pair(args):
    opp, seed, k, brain_cfg = args
    v = load_variant("discard_holdem")
    cfg = dict({"lock_enabled": False, "river_budget_s": TimingConfig().river_budget_s * k}, **brain_cfg)
    out = 0
    for first in (0, 1):
        me = PlayerSpec.brain("tier3x", cfg).build()
        op = PlayerSpec.brain(opp).build()
        players, scales = ([me, op], [1.0 / k, 1.0]) if first == 0 else ([op, me], [1.0, 1.0 / k])
        m = play_match(players, v, seed=seed, hands=200, time_bank_s=30.0, clock_scale=scales, reply_limit_s=5.0)
        out += m.chips[first]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--opponents", default="d_new_exploiter,d_conv_opp3,d_new_lag")
    ap.add_argument("--pairs", type=int, default=30)
    ap.add_argument("--first-seed", type=int, default=92000)
    ap.add_argument("--speeds", default="1,4")
    ap.add_argument("--processes", type=int, default=3)
    a = ap.parse_args()
    ks = [float(x) for x in a.speeds.split(",")]
    with Pool(a.processes) as pool:
        for opp in a.opponents.split(","):
            res = {k: pool.map(pair, [(opp, a.first_seed + i, k, {}) for i in range(a.pairs)]) for k in ks}
            base = res[ks[0]]
            for k in ks[1:]:
                d = [(x - y) / 400.0 for x, y in zip(res[k], base)]
                mu = sum(d) / len(d)
                se = math.sqrt(sum((x - mu) ** 2 for x in d) / max(1, len(d) - 1) / len(d))
                print(f"{opp}: speed x{k:g} vs x{ks[0]:g}: {mu:+.3f} +- {se:.3f} chips/hand (paired, {a.pairs} pairs); "
                      f"x{ks[0]:g} {sum(base) / 400 / len(base):+.2f}/hand", flush=True)


if __name__ == "__main__":
    main()
