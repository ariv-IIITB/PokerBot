"""Duplicate pairs (= two-leg matches) of A vs B with a running 2-leg score every N pairs.

    .venv/bin/python -m lab.stream_pairs tier3x d_v16 --pairs 100 --every 10 --first-seed 99500"""
from __future__ import annotations

import argparse
import math
from multiprocessing import Pool

from lab.harness import load_variant, play_pair
from lab.players import PlayerSpec


def one(args):
    a, b, seed, hands, bank = args
    return play_pair(PlayerSpec.brain(a), PlayerSpec.brain(b), load_variant("discard_holdem"), seed, hands,
                     time_bank_s=bank)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--pairs", type=int, default=100)
    ap.add_argument("--every", type=int, default=10)
    ap.add_argument("--first-seed", type=int, default=99500)
    ap.add_argument("--hands", type=int, default=200)
    ap.add_argument("--bank", type=float, default=30.0)
    ap.add_argument("--processes", type=int, default=3)
    a = ap.parse_args()
    w = l = d = ff = 0
    chips = 0
    hands = 0
    with Pool(a.processes) as pool:
        tasks = [(a.a, a.b, a.first_seed + i, a.hands, a.bank) for i in range(a.pairs)]
        for n, p in enumerate(pool.imap(one, tasks), 1):
            if p.forfeits[0] or p.forfeits[1]:
                ff += 1
                win = p.forfeits[1] > p.forfeits[0]
                w, l = w + int(win), l + int(not win)
            else:
                t = sum(p.a_chips)
                w, l, d = w + int(t > 0), l + int(t < 0), d + int(t == 0)
            chips += sum(p.a_chips)
            hands += p.hands
            if n % a.every == 0 or n == a.pairs:
                s = (w + 0.5 * d) / n
                se = math.sqrt(max(s * (1 - s), 1e-9) / n)
                print(f"after {n:3d} matches: {a.a} {w}-{l}" + (f"-{d}" if d else "")
                      + f"  score {s:.3f} +- {se:.3f}  chips/hand {chips / max(1, hands):+.2f}"
                      + (f"  forfeits {ff}" if ff else ""), flush=True)


if __name__ == "__main__":
    main()
