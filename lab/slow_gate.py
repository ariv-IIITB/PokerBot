"""I1 timing gate: bank use of a brain on a machine twice as slow (the lab clock charges every second twice; the
river solver's wall-clock box is halved to match, as lab/rc_ratio.py and tests/test_river_timing.py do).
Uses the current rules: 200 hands / 30 s (Stage 1 leg) and 500 hands / 75 s (Stage 2 leg).

    .venv/bin/python -m lab.slow_gate tier3x 'tier3x:{"x_selfdef":true}' --opponents calling_station,d_new_lag --seeds 3

Pass: worst leg <= 50 % of the bank at 2x, no forfeit, no emergency decisions."""
from __future__ import annotations

import argparse
import json

from bot.timing import TimingConfig
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec


def leg(name: str, cfg: dict, opp: str, hands: int, bank: float, seed: int, scale: float):
    t = TimingConfig()
    c = dict({"lock_enabled": False, "river_budget_s": t.river_budget_s / scale}, **cfg)
    a = PlayerSpec.brain(name, c).build()
    m = play_match([a, PlayerSpec.brain(opp).build()], load_variant("discard_holdem"), seed=seed, hands=hands,
                   time_bank_s=bank, clock_scale=scale, reply_limit_s=5.0)
    return 100.0 * (bank - m.bank_left[0]) / bank, m.worst_decision_s[0], a.bot.deadline_hits, a.bot.emergency_decisions


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("brains", nargs="+", help="name or name:{json}")
    ap.add_argument("--opponents", default="calling_station,d_new_lag,d_new_trapper,maniac")
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--first-seed", type=int, default=60000)
    ap.add_argument("--scale", type=float, default=2.0)
    ap.add_argument("--stages", default="200:30,500:75")
    a = ap.parse_args()
    for spec in a.brains:
        name, _, js = spec.partition(":")
        cfg = json.loads(js) if js else {}
        for st in a.stages.split(","):
            hands, bank = int(st.split(":")[0]), float(st.split(":")[1])
            rows = [leg(name, cfg, o, hands, bank, a.first_seed + s, a.scale)
                    for o in a.opponents.split(",") for s in range(a.seeds)]
            used = [r[0] for r in rows]
            print(f"{spec} {hands}h/{bank:g}s x{a.scale:g}: bank used mean {sum(used) / len(used):.1f}% "
                  f"max {max(used):.1f}%; worst reply {max(r[1] for r in rows) * 1e3:.0f} ms; "
                  f"deadline hits {sum(r[2] for r in rows)}; emergency {sum(r[3] for r in rows)} "
                  f"({len(rows)} legs) {'PASS' if max(used) <= 50 and sum(r[3] for r in rows) == 0 else 'FAIL'}",
                  flush=True)


if __name__ == "__main__":
    main()
