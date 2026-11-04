"""RC task B check: how long does Tier 3 (river solver on) take at budget 0, and is its action legal / sensible?
Before every real decision it also asks `brain.decide(state, legal, 0.0)` (timed, legality-checked, by street).

    .venv/bin/python -m lab.rc_budget0 --hands 400"""
import argparse
import time
from collections import defaultdict

import numpy as np

from bot.actions import is_legal
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--opponents", default="calling_station,d_new_trapper,d_conv_opp3")
    a = ap.parse_args()
    cfg = {"lock_enabled": False, "t3_river_solver": True}
    by = defaultdict(list)
    bad = errs = 0
    for opp in a.opponents.split(","):
        p = PlayerSpec.brain("tier3", dict(cfg)).build()
        bot = p.bot
        orig = bot.choose

        def probe(legal, bot=bot, orig=orig):
            nonlocal bad, errs
            h = bot.state.hand
            street = "special" if legal.can_special else f"board{len(h.board) if h is not None else '?'}"
            t0 = time.perf_counter()
            try:
                act = bot.brain.decide(bot.state, legal, 0.0)
                ok = is_legal(act, legal) or legal.can_special
            except BaseException as e:
                errs += 1
                act, ok = None, False
                print("EXC", repr(e)[:100])
            by[street].append(time.perf_counter() - t0)
            bad += (not ok)
            return orig(legal)

        bot.choose = probe
        play_match([p, PlayerSpec.brain(opp).build()], load_variant("discard_holdem"), seed=30000,
                   hands=a.hands, time_bank_s=60.0, reply_limit_s=5.0)
    for k, v in sorted(by.items()):
        v = np.array(v) * 1e3
        print(f"{k:8} n={len(v):5} ms: p50 {np.median(v):.2f} p99 {np.percentile(v, 99):.2f} max {v.max():.2f}")
    print(f"illegal or failed at budget 0: {bad} (exceptions {errs})")


if __name__ == "__main__":
    main()
