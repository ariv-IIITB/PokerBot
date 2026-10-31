"""Build the opponent type library for the bot's type posterior (build map X2; lab only).

A type is one recorded bot (or several that play identically), labelled with its style family. Per type: P(action | street, facing our bet)
from their recorded decisions (bot.strategy.traits.classify, the bot's own event view), add-one
smoothed, plus the slow traits a short match cannot measure (share of shown river bets that were
weak; river bets when not facing a bet). "unknown" is the population average flattened toward
uniform, so a style outside the library lands there instead of being matched with confidence.

    .venv/bin/python -m lab.opps.types RECORD_DIR [--skip-pairs 2] [--out data/discard_holdem/types.json]

Only training-pool and sparring bots are used (never held-out bots). The first --skip-pairs
duplicate pairs of every recording are left out: they are the committed test fixtures
(tests/fixtures/opp_records/), which then serve as held-out seeds.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

from bot.strategy.traits import classify
from bot.strategy.types import ACTS, N_CTX, context_index
from lab.opps import record, traits

# type -> (family, member bots). One type per bot (bots that play identically share one), so a
# known bot's distance to its own type is sampling noise; the family names the style.
TYPES: dict[str, tuple[str, list[str]]] = {
    "exploiter": ("overfolder", ["d_new_exploiter"]),
    "conv_opp3": ("overfolder", ["d_conv_opp3"]),
    "rules": ("overfolder", ["d_new_rules"]),
    "minraise": ("valueonly", ["d_new_minraise"]),
    "tight": ("nit", ["tight"]),
    "station": ("station", ["starter", "calling_station"]),
    "trapper": ("trapper", ["d_new_trapper"]),
    "lag": ("aggressor", ["d_new_lag"]),
    "maniac": ("aggressor", ["maniac"]),
}
UNKNOWN_FLATTEN = 0.5          # unknown = (1 - f) * population + f * uniform


def act_counts(hands: Iterable[dict]) -> np.ndarray:
    """(N_CTX, len(ACTS)) counts of the opponent's actions per context."""
    c = np.zeros((N_CTX, len(ACTS)))
    for rec in hands:
        hs = record.to_hand_state(rec)
        for i in range(len(hs.history)):
            ev = classify(hs.history[: i + 1])
            if ev is not None:
                ctx, act = context_index(ev)
                c[ctx, act] += 1
    return c


def build(record_dir: Path, skip_pairs: int = 2) -> dict:
    lib: dict = {"types": {}, "acts": list(ACTS), "n_ctx": N_CTX}
    pop = np.zeros((N_CTX, len(ACTS)))
    slow_all: list = []
    for name, (family, bots) in TYPES.items():
        counts = np.zeros((N_CTX, len(ACTS)))
        hands: list = []
        for bot in bots:
            data = record.load(record_dir / f"{bot}.json.gz")
            data = dict(data, pairs=data["pairs"][skip_pairs:])
            hs = list(record.iter_hands(data))
            hands += hs
            counts += act_counts(hs)
        prof = traits.profile(hands)
        slow = {"river_bluff": prof["weak_river_bet"].value or 0.0,
                "river_bet": prof["bet_river"].value or 0.0}
        slow_all.append((prof["weak_river_bet"], prof["bet_river"]))
        pop += counts / max(1, len(bots))
        probs = (counts + 1) / (counts.sum(axis=1, keepdims=True) + len(ACTS))
        lib["types"][name] = {"family": family, "members": bots, "probs": probs.round(5).tolist(),
                              "slow": slow, "decisions": int(counts.sum())}
    pop_p = (pop + 1) / (pop.sum(axis=1, keepdims=True) + len(ACTS))
    unknown = (1 - UNKNOWN_FLATTEN) * pop_p + UNKNOWN_FLATTEN / len(ACTS)
    weak_h = sum(w.hits for w, _ in slow_all)
    weak_n = sum(w.n for w, _ in slow_all)
    bet_h = sum(b.hits for _, b in slow_all)
    bet_n = sum(b.n for _, b in slow_all)
    lib["types"]["unknown"] = {"family": "unknown", "members": [], "probs": unknown.round(5).tolist(),
                               "slow": {"river_bluff": weak_h / max(1, weak_n),
                                        "river_bet": bet_h / max(1, bet_n)}, "decisions": 0}
    return lib


def main(argv: Optional[list[str]] = None) -> int:
    from lab.harness import load_variant
    from variant.spec import spec_hash
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("records")
    ap.add_argument("--skip-pairs", type=int, default=2)
    ap.add_argument("--variant", default="discard_holdem")
    ap.add_argument("--out", default="data/discard_holdem/types.json")
    args = ap.parse_args(argv)
    lib = build(Path(args.records), args.skip_pairs)
    lib["spec_hash"] = spec_hash(load_variant(args.variant))
    lib["built_from"] = f"lab.opps.record, Tier 3 lock off, pairs {args.skip_pairs}+ of each recording"
    Path(args.out).write_text(json.dumps(lib, indent=1) + "\n")
    for name, t in lib["types"].items():
        print(f"{name:11} decisions {t['decisions']:6}  river bluff {t['slow']['river_bluff']:.0%}  "
              f"river bet {t['slow']['river_bet']:.0%}")
    print(f"-> {args.out} ({Path(args.out).stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
