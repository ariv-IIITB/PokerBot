"""RC: bank use of Tier 3 with the river solver vs without, on a machine twice as slow (the lab clock charges
every second twice; the solver's wall-clock box is halved to match, as tests/test_river_timing.py does).

    flock ... .venv/bin/python -m lab.rc_ratio --boxes 0.04,0.08 --hands 400 [--seed 30000]

`--boxes` = river_budget_s as it would ship (server wall-clock seconds); box_mult is scaled like the test does."""
import argparse
import math

from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec
from bot.timing import TimingConfig


def run(cfg: dict, hands: int, bank: float, opponent: str, seed: int):
    a = PlayerSpec.brain("tier3", dict({"lock_enabled": False}, **cfg)).build()
    m = play_match([a, PlayerSpec.brain(opponent).build()], load_variant("discard_holdem"), seed=seed,
                   hands=hands, time_bank_s=bank, clock_scale=2.0, reply_limit_s=5.0)
    return m, a.bot, a.bot.brain


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boxes", default="0.04")
    ap.add_argument("--mults", default="", help="river_box_mult values as they would ship (default: TimingConfig's)")
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--opponents", default="calling_station,d_new_trapper")
    ap.add_argument("--seed", type=int, default=30000)
    a = ap.parse_args()
    bank = 60.0 if a.hands <= 400 else 150.0
    mults = [float(v) for v in a.mults.split(",")] if a.mults else [TimingConfig().river_box_mult]
    for opp in a.opponents.split(","):
        m0, b0, _ = run({}, a.hands, bank, opp, a.seed)
        u0 = bank - m0.bank_left[0]
        for x, mult in ((float(v), mu) for v in a.boxes.split(",") for mu in mults):
            m1, b1, br = run({"t3_river_solver": True, "river_budget_s": x / 2, "river_box_mult": mult / 2},
                             a.hands, bank, opp, a.seed)
            u1 = bank - m1.bank_left[0]
            st = br.stats
            print(f"{opp} {a.hands}h box {x * 1e3:.0f} ms x{mult:g}: used {u0:.1f}s -> {u1:.1f}s (x{u1 / u0:.3f}; {100 * u1 / bank:.0f}% of bank); "
                  f"deadline hits {b0.deadline_hits} -> {b1.deadline_hits} (limit {b0.deadline_hits + 2 * math.sqrt(b0.deadline_hits):.1f}); "
                  f"worst reply {m1.worst_decision_s[0] * 1e3:.0f} ms; emergency {b1.emergency_decisions}; "
                  f"solves {st['river_solves']}, {st['river_iters'] / max(1, st['river_solves']):.0f} passes, "
                  f"fallbacks {st['river_fallbacks']} (few {st['river_few_iters']}, nopass {st['river_no_pass']}, err {st['river_errors']})", flush=True)


if __name__ == "__main__":
    main()
