"""RC task A: wall time of every river decision against that decision's hard limit (shipped river config,
the 2x-slower stand-in: engine clock x2, solver box halved as in lab.rc_ratio). Run under the exclusive lock.

    .venv/bin/python -m lab.rc_margin --hands 400 [--opponents calling_station,d_new_trapper]

The stand-in only changes the clock the bank is charged on; a decision's real server time is ~2 x the laptop time
(solver box excepted, which is wall-clock and was halved), so the table gives laptop ms and ms x2 next to the limit."""
import argparse
import time

import numpy as np

from bot.timing import TimingConfig
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--opponents", default="calling_station,d_new_trapper")
    ap.add_argument("--seed", type=int, default=30000)
    a = ap.parse_args()
    c = TimingConfig()
    bank = 60.0 if a.hands <= 400 else 150.0
    cfg = {"lock_enabled": False, "t3_river_solver": True, "river_budget_s": c.river_budget_s / 2,
           "river_box_mult": c.river_box_mult / 2}
    for opp in a.opponents.split(","):
        p = PlayerSpec.brain("tier3", dict(cfg)).build()
        rows = []                                    # (wall, hard limit, is river)
        bot = p.bot
        orig = bot.choose

        def timed(legal, bot=bot, orig=orig, rows=rows):
            h = bot.state.hand
            river = h is not None and len(h.board) == 5
            lim = bot.timer.hard_limit(bot.timer.budget(bot.state.hands_remaining))
            t0 = time.perf_counter()
            r = orig(legal)
            rows.append((time.perf_counter() - t0, lim, river))
            return r

        bot.choose = timed
        m = play_match([p, PlayerSpec.brain(opp).build()], load_variant("discard_holdem"), seed=a.seed,
                       hands=a.hands, time_bank_s=bank, clock_scale=2.0, reply_limit_s=5.0)
        for name, sel in (("river", True), ("other", False)):
            r = np.array([(w, l) for w, l, rv in rows if rv == sel])
            if not len(r):
                continue
            w, l = r[:, 0], r[:, 1]
            f = w / l
            print(f"{opp} {a.hands}h {name:5} n={len(r)}: wall ms p50 {np.median(w) * 1e3:.1f} p99 {np.percentile(w, 99) * 1e3:.1f} "
                  f"max {w.max() * 1e3:.1f} | x2: p99 {2e3 * np.percentile(w, 99):.1f} max {2e3 * w.max():.1f} | "
                  f"hard limit min {l.min() * 1e3:.1f} median {np.median(l) * 1e3:.1f} | wall/limit max {f.max():.2f} (x2: {2 * f.max():.2f}) "
                  f"p99 {np.percentile(f, 99):.2f}; deadline hits {bot.deadline_hits}", flush=True)


if __name__ == "__main__":
    main()
