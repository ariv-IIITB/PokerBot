"""Audit: how much does a brain win against each sparring bot, per variant?

Runs duplicate matches of `brain` vs every sparring bot on several catalog variants, with
the endgame lock on (as shipped) and off (shows the real per-hand edge: with the lock on,
the bot stops playing once the match is won, which caps chips/hand). Prints a table.

    .venv/bin/python -m lab.sparring_audit --variants holdem_nl mit2026_discard --seeds 8
"""
from __future__ import annotations

import argparse
import json
from typing import Optional

from lab.harness import load_variant, run_duplicate
from lab.players import PlayerSpec

SPARRING = ["random_legal", "all_in", "calling_station", "tight", "maniac"]
DEFAULT_VARIANTS = ["holdem_nl", "mit2026_discard", "omaha", "short_deck", "fl_holdem",
                    "lowball_27", "auction_card", "three_boards"]


def audit(brain: str, variants: list[str], opponents: list[str], seeds: int, hands: int,
          lock_modes: tuple[bool, ...] = (True, False), extra: Optional[dict] = None) -> list[dict]:
    rows = []
    for v in variants:
        spec = load_variant(v)
        for opp in opponents:
            row = {"variant": v, "opponent": opp}
            for lock in lock_modes:
                cfg = dict(extra or {})
                cfg["lock_enabled"] = lock
                rep = run_duplicate(PlayerSpec.brain(brain, cfg), PlayerSpec.brain(opp), spec,
                                    seeds=range(seeds), hands=hands)
                cph, se = rep.chips_per_hand
                wr, _ = rep.match_win_rate
                tag = "lock" if lock else "nolock"
                row[f"{tag}_cph"], row[f"{tag}_se"], row[f"{tag}_win"] = cph, se, wr
            rows.append(row)
            print(fmt_row(row), flush=True)
    return rows


def fmt_row(r: dict) -> str:
    parts = [f"{r['variant']:<16} {r['opponent']:<16}"]
    for tag in ("lock", "nolock"):
        if f"{tag}_cph" in r:
            parts.append(f"{tag}: {r[tag + '_cph']:+7.2f} ± {r[tag + '_se']:.2f} "
                         f"(win {r[tag + '_win']:.2f})")
    return " | ".join(parts)


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--brain", default="tier2")
    ap.add_argument("--variants", nargs="+", default=DEFAULT_VARIANTS)
    ap.add_argument("--opponents", nargs="+", default=SPARRING)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--lock-only", action="store_true")
    ap.add_argument("--no-lock-only", action="store_true")
    ap.add_argument("--set", nargs="*", default=[], help="brain overrides, e.g. inference=false")
    args = ap.parse_args(argv)
    modes = (True,) if args.lock_only else ((False,) if args.no_lock_only else (True, False))
    extra = {}
    for kv in args.set:
        k, _, v = kv.partition("=")
        extra[k] = json.loads(v)
    audit(args.brain, args.variants, args.opponents, args.seeds, args.hands, modes, extra)


if __name__ == "__main__":
    main()
