"""Engine throughput: in-process hands/second (single process).

Usage: .venv/bin/python -m lab.bench_engine
"""
from __future__ import annotations

import time

from lab.engine import play_match
from lab.example_variants import EXAMPLES
from lab.players import PlayerSpec

PAIRS = [("tier0", "tier0"), ("random_legal", "calling_station"), ("maniac", "calling_station")]


def bench(a: str, b: str, variant: str = "holdem", hands: int = 3000) -> float:
    players = [PlayerSpec.brain(a).build(), PlayerSpec.brain(b).build()]
    t0 = time.perf_counter()
    m = play_match(players, EXAMPLES[variant], seed=1, hands=hands, time_bank_s=1e9)
    return m.hands_played / (time.perf_counter() - t0)


def main() -> None:
    for variant in ("holdem", "discard3"):
        for a, b in PAIRS:
            print(f"{variant:<9} {a:>13} vs {b:<16} {bench(a, b, variant):>8,.0f} hands/s")


if __name__ == "__main__":
    main()
