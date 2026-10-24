"""Parameter sweep: grid or random search over a brain's config, ranked by duplicate results.

The space file is JSON, one entry per parameter:
    {"bluff_freq": [0.0, 0.1, 0.2],                  # list -> these values
     "call_margin": {"low": -0.02, "high": 0.06},    # range -> uniform (random mode)
     "raise_equity": [[0.7, 0.68, 0.7, 0.74], [0.65, 0.65, 0.68, 0.72]]}
Grid mode takes the product of lists (ranges are sampled `--grid-points` times evenly).
Every candidate plays the same seeds against every opponent in the pool (common random
numbers), and is ranked by mean chips/hand across the pool, with a standard error.

CLI:  .venv/bin/python -m lab.sweep tier2 space.json --opponents tier1 maniac tight \
          --seeds 8 --hands 200 --mode random --n 12
Results are also written to results/sweep_<timestamp>.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from lab.harness import run_duplicate
from lab.players import ROOT, PlayerSpec


@dataclass
class Candidate:
    params: dict[str, Any]
    chips_per_hand: float = 0.0
    se: float = 0.0
    match_score: float = 0.0
    per_opponent: Optional[dict[str, float]] = None


def _axis(spec: Any, points: int) -> list:
    if isinstance(spec, list):
        return spec
    if isinstance(spec, dict) and {"low", "high"} <= set(spec):
        lo, hi = float(spec["low"]), float(spec["high"])
        return [lo + (hi - lo) * i / max(1, points - 1) for i in range(points)]
    return [spec]


def grid(space: dict[str, Any], points: int = 3) -> list[dict[str, Any]]:
    keys = list(space)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(_axis(space[k], points) for k in keys))]


def random_candidates(space: dict[str, Any], n: int, seed: int = 0) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        c = {}
        for k, spec in space.items():
            if isinstance(spec, dict) and {"low", "high"} <= set(spec):
                c[k] = rng.uniform(float(spec["low"]), float(spec["high"]))
            elif isinstance(spec, list):
                c[k] = rng.choice(spec)
            else:
                c[k] = spec
        out.append(c)
    return out


def evaluate(brain: str, params: dict[str, Any], opponents: Sequence[PlayerSpec],
             seeds: Sequence[int], hands: int, processes: Optional[int],
             time_bank_s: Optional[float]) -> Candidate:
    cand = Candidate(params, per_opponent={})
    means, ses, scores = [], [], []
    for opp in opponents:
        rep = run_duplicate(PlayerSpec.brain(brain, params, label=brain), opp, seeds=seeds,
                            hands=hands, processes=processes, time_bank_s=time_bank_s)
        m, se = rep.chips_per_hand
        means.append(m)
        ses.append(se)
        scores.append(rep.match_win_rate[0])
        cand.per_opponent[opp.display] = m  # type: ignore[index]
    k = len(opponents)
    cand.chips_per_hand = sum(means) / k
    cand.se = math.sqrt(sum(s * s for s in ses)) / k
    cand.match_score = sum(scores) / k
    return cand


def run_sweep(brain: str, space: dict[str, Any], opponents: Sequence[str],
              seeds: Sequence[int] = range(8), hands: int = 200, mode: str = "grid",
              n: int = 10, grid_points: int = 3, processes: Optional[int] = None,
              time_bank_s: Optional[float] = None, seed: int = 0,
              include_baseline: bool = True) -> list[Candidate]:
    cands = grid(space, grid_points) if mode == "grid" else random_candidates(space, n, seed)
    if include_baseline:
        cands = [{}] + cands          # {} = the brain's current config
    pool = [PlayerSpec.brain(o) for o in opponents]
    results = [evaluate(brain, c, pool, list(seeds), hands, processes, time_bank_s) for c in cands]
    return sorted(results, key=lambda c: c.chips_per_hand, reverse=True)


def format_table(results: Sequence[Candidate]) -> str:
    lines = [f"{'rank':>4}  {'chips/hand':>16}  {'score':>5}  params"]
    for i, c in enumerate(results, 1):
        p = json.dumps(c.params) if c.params else "(baseline)"
        lines.append(f"{i:>4}  {c.chips_per_hand:+8.3f} ± {c.se:5.3f}  {c.match_score:5.3f}  {p}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Sweep a brain's parameters.")
    ap.add_argument("brain")
    ap.add_argument("space", help="JSON parameter space file")
    ap.add_argument("--opponents", nargs="+", default=["tier1", "maniac", "tight", "calling_station"])
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--hands", type=int, default=200)
    ap.add_argument("--mode", choices=["grid", "random"], default="grid")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--grid-points", type=int, default=3)
    ap.add_argument("--processes", type=int, default=None)
    ap.add_argument("--bank", type=float, default=None)
    args = ap.parse_args(argv)
    space = json.loads(Path(args.space).read_text())
    results = run_sweep(args.brain, space, args.opponents, range(args.seeds), args.hands,
                        args.mode, args.n, args.grid_points, args.processes, args.bank)
    print(format_table(results))
    out = ROOT / "results" / f"sweep_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps([c.__dict__ for c in results], indent=2))
    print(f"written to {out}")


if __name__ == "__main__":
    main()
