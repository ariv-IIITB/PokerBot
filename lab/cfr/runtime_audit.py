"""Play a CFR brain against an opponent in duplicate and report how its betting decisions
were made: from the table, off-tree (key missing / action-count mismatch), with a
translated opponent bet in the history, or by the Tier 2 fallback (endgame lock, hand not
rebuildable). Also reports chips/hand and match score (lab only).

    .venv/bin/python -m lab.cfr.runtime_audit --strategy results/p23/hunl/cfr_strategy.json \
        --variant holdem_nl --opponent tier2 --seeds 64 --hands 400
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
from typing import Optional

from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec
from lab.stats import mean_se


def _pair(args) -> dict:
    """One duplicate pair; returns A's chips, scores, and the CFR brain's decision stats."""
    a_spec, b_spec, variant, seed, hands = args
    spec = load_variant(variant)
    out = {"chips": 0, "hands": 0, "scores": [], "stats": {}}
    for seat in (0, 1):
        a, b = a_spec.build(), b_spec.build()
        players = [a, b] if seat == 0 else [b, a]
        m = play_match(players, spec, seed, hands)
        out["chips"] += m.chips[seat]
        out["hands"] += m.hands_played
        out["scores"].append(m.score(seat))
        for k, v in getattr(a.bot.brain, "stats", {}).items():
            out["stats"][k] = out["stats"].get(k, 0) + v
    return out


def audit(strategy: str, variant: str, opponent: str, seeds: int, hands: int,
          cfg: Optional[dict] = None, opp_cfg: Optional[dict] = None,
          processes: Optional[int] = None, first_seed: int = 0) -> dict:
    a_cfg = {"strategy_file": strategy, "lock_enabled": False}
    a_cfg.update(cfg or {})
    a = PlayerSpec.brain("cfr", a_cfg, label="cfr")
    b = PlayerSpec.brain(opponent, opp_cfg, label=opponent)
    tasks = [(a, b, variant, s, hands) for s in range(first_seed, first_seed + seeds)]
    with mp.get_context("spawn").Pool(processes or os.cpu_count() or 1) as pool:
        rows = pool.map(_pair, tasks, chunksize=1)
    cph, se = mean_se([r["chips"] / max(1, r["hands"]) for r in rows])
    win, wse = mean_se([s for r in rows for s in r["scores"]])
    stats: dict = {}
    for r in rows:
        for k, v in r["stats"].items():
            stats[k] = stats.get(k, 0) + v
    decisions = sum(stats.get(k, 0) for k in ("no_rec", "hit", "miss_key", "miss_len"))
    frac = {k: v / max(1, decisions) for k, v in stats.items()}
    return {"strategy": strategy, "variant": variant, "opponent": opponent,
            "hands": sum(r["hands"] for r in rows), "chips_per_hand": cph, "se": se,
            "match_score": win, "match_se": wse, "decisions": decisions, "counts": stats,
            "fractions": frac}


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--variant", default="holdem_nl")
    ap.add_argument("--opponent", default="tier2")
    ap.add_argument("--seeds", type=int, default=64)
    ap.add_argument("--first-seed", type=int, default=0)
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--processes", type=int, default=None)
    ap.add_argument("--lock", action="store_true", help="CFR side keeps the endgame lock")
    args = ap.parse_args(argv)
    res = audit(args.strategy, args.variant, args.opponent, args.seeds, args.hands,
                {"lock_enabled": args.lock}, processes=args.processes, first_seed=args.first_seed)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
