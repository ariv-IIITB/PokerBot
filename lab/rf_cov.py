"""RF: share of river decisions that get a full solve with the SHIPPED wall-clock box (no pinned passes), at the real clock
and at the 2x slower stand-in (box halved, bank charged twice, as lab/rc_ratio.py). Run under the exclusive lock.

    flock /tmp/pokerbot_turnstile.lock flock -x /tmp/pokerbot_laptop.lock .venv/bin/python -m lab.rf_cov [--extra JSON]
full = solved with >= river_min_iters passes; few = fewer passes (Tier 3's river plays); nopass/missing/err = also Tier 3's river.
"""
import argparse
import json

from bot.timing import TimingConfig
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--opponents", default="calling_station,d_new_trapper,d_conv_opp3")
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--seed", type=int, default=73900)
    ap.add_argument("--extra", default="{}")
    ap.add_argument("--brain", default="tier3x")
    a = ap.parse_args()
    t = TimingConfig()
    for opp in a.opponents.split(","):
        for scale in (1.0, 2.0):
            cfg = dict({"lock_enabled": False, "t3_river_solver": True, "river_budget_s": t.river_budget_s / scale,
                        "river_box_mult": t.river_box_mult / scale}, **json.loads(a.extra))
            p = PlayerSpec.brain(a.brain, cfg).build()
            m = play_match([p, PlayerSpec.brain(opp).build()], load_variant("discard_holdem"), seed=a.seed, hands=a.hands,
                           time_bank_s=60.0 if a.hands <= 400 else 150.0, clock_scale=scale, reply_limit_s=5.0)
            st = p.bot.brain.stats
            tot = st["river_solves"] + st["river_no_pass"] + st["river_missing"] + st["river_errors"]
            full = st["river_solves"] - st["river_few_iters"]
            print(f"{opp:16} clock x{scale:g}: river decisions {tot}, full solve {100 * full / max(1, tot):.1f}% "
                  f"(few {st['river_few_iters']}, nopass {st['river_no_pass']}, missing {st['river_missing']}, err {st['river_errors']}); "
                  f"{st['river_iters'] / max(1, st['river_solves']):.0f} passes/solve; deadline hits {p.bot.deadline_hits}", flush=True)


if __name__ == "__main__":
    main()
