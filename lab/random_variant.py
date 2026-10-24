"""Random valid variant specs across the taxonomy (seeded), for fuzzing.

Each feature is tagged with the phase whose plugin implements it; `max_phase` limits the
generator to what is built so far. `supported_only=True` additionally keeps only specs
the compiler accepts.

CLI:  .venv/bin/python -m lab.random_variant --seed 3 --count 5       (prints JSON specs)
"""
from __future__ import annotations

import argparse
import json
import random
from typing import Optional

from bot.game.compile import NotSupported, compile_spec
from variant.spec import STANDARD_RANKS, VariantSpec

ROUND_NAMES = ["preflop", "flop", "turn", "river", "fifth", "sixth"]


def _program(r: random.Random, hole: int, streets: list[int], max_phase: int) -> list[dict]:
    prog: list[dict] = [{"type": "post_blinds"}, {"type": "deal_hole", "n": hole}]
    burn = r.random() < 0.2
    for i, n in enumerate(streets):
        if i:
            step = {"type": "deal_board", "n": n}
            if burn:
                step.update(burn=1, burn_revealed=r.random() < 0.5)
            prog.append(step)
        bet = {"type": "betting", "round": ROUND_NAMES[i] if i < len(ROUND_NAMES) else f"r{i}"}
        if r.random() < 0.15:
            bet["first"] = r.choice(["SB", "BB"])
        prog.append(bet)
    prog.append({"type": "showdown"})
    return prog


def random_spec(seed: int, max_phase: int = 99) -> VariantSpec:
    """One random spec that passes validate(). Retries internally until valid."""
    r = random.Random(seed)
    for attempt in range(200):
        d: dict = {"name": f"random_{seed}_{attempt}", "description": "randomly generated"}
        deck: dict = {}
        ranks = STANDARD_RANKS
        if max_phase >= 12 and r.random() < 0.15:
            ranks = STANDARD_RANKS[r.randint(1, 4):]          # short decks
            deck["ranks"] = ranks
        if r.random() < 0.15:
            deck["removed"] = [f"{r.choice(ranks)}{r.choice('cdhs')}" for _ in range(r.randint(1, 4))]
            deck["removed"] = sorted(set(deck["removed"]))
        if max_phase >= 12 and r.random() < 0.1:
            deck["jokers"] = r.randint(1, 2)
        if deck:
            d["deck"] = deck

        hole = r.choice([1, 2, 2, 2, 3, 4, 5, 6])
        n_rounds = r.randint(1, 5)
        streets = [0] + [r.choice([0, 1, 1, 2, 3]) for _ in range(n_rounds - 1)]
        d["program"] = _program(r, hole, streets, max_phase)

        ev: dict = {}
        board = sum(streets)
        if r.random() < 0.2:
            ev["hand_size"] = r.randint(3, 5)
        k = ev.get("hand_size", 5)
        if hole >= 2 and r.random() < 0.25 and board >= k - 2:
            ev["hole_exact"] = 2
        if max_phase >= 12 and r.random() < 0.2:
            ev["kind"] = r.choice(["low_a5", "low_27", "hilo"])
            if ev["kind"] == "hilo":
                ev["low_qualifier"] = 8
        if deck.get("jokers"):
            ev["wild"] = {"jokers": True}
        elif max_phase >= 12 and r.random() < 0.1 and "2" in ranks:
            ev["wild"] = {"rank": "2"}
        if max_phase >= 12 and r.random() < 0.1 and ev.get("kind", "high") in ("high", "hilo"):
            order = ["high_card", "pair", "two_pair", "trips", "straight", "flush",
                     "full_house", "quads", "straight_flush"]
            i = r.randint(1, 7)
            order[i], order[i + 1] = order[i + 1], order[i]
            ev["category_order"] = order
        if ev:
            d["evaluation"] = ev

        bet: dict = {}
        if r.random() < 0.3:
            bb = r.choice([2, 4, 10, 20])
            bet.update(small_blind=bb // 2, big_blind=bb)
        if r.random() < 0.3:
            bet["max_raises"] = r.randint(0, 4)
        if r.random() < 0.15:
            bet["postflop_first"] = "SB"
        if max_phase >= 14 and r.random() < 0.3:
            bet["structure"] = r.choice(["PL", "FL"])
            if bet["structure"] == "FL":
                bb = bet.get("big_blind", 2)
                bet["fixed_bets"] = [bb] * 2 + [2 * bb] * 8
        if bet:
            d["betting"] = bet

        match: dict = {}
        bb = bet.get("big_blind", 2)
        if r.random() < 0.4:
            match["starting_stack"] = bb * r.choice([3, 10, 50, 100, 200, 500])
        if r.random() < 0.2:
            match["reset_stacks"] = False
        if match:
            d["match"] = match

        spec = VariantSpec.from_dict(d)
        if not spec.validate():
            return spec
    raise RuntimeError(f"no valid random spec for seed {seed}")


def random_supported_spec(seed: int, max_phase: int = 99) -> VariantSpec:
    """Like random_spec, but only specs the current compiler supports."""
    for k in range(500):
        spec = random_spec(seed * 1000 + k, max_phase)
        try:
            compile_spec(spec)
            return spec
        except NotSupported:
            continue
    raise RuntimeError(f"no supported random spec near seed {seed}")


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Print random valid variant specs.")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--supported", action="store_true", help="only specs the compiler accepts")
    args = ap.parse_args(argv)
    for i in range(args.count):
        fn = random_supported_spec if args.supported else random_spec
        print(json.dumps(fn(args.seed + i).to_dict(), indent=2))


if __name__ == "__main__":
    main()
