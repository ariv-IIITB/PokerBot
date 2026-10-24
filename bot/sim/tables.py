"""Optional precomputed data (built offline by lab/precompute.py), loaded read-only.

Layout: <data dir>/<variant name>/meta.json + .npy files. The bot looks in
$POKERBOT_DATA (if set) and <repo>/data/. A table is used only if meta.json's spec hash
matches the active variant's; anything missing, unreadable or mismatched means "no
tables" and the bot computes live instead. Nothing is ever written at runtime.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from bot.log import log
from bot.sim.canonical import ClassIndex

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Tables:
    meta: dict
    classes: ClassIndex
    eq_random: np.ndarray                 # per class: share vs a random hand from the start
    eq_range: Optional[np.ndarray] = None # per class: share vs the top-X% range

    def start_share(self, hole) -> float:
        return float(self.eq_random[self.classes.class_of(hole)])


def _candidates(name: str) -> list[Path]:
    dirs = []
    if os.environ.get("POKERBOT_DATA"):
        dirs.append(Path(os.environ["POKERBOT_DATA"]))
    dirs.append(ROOT / "data")
    return [d / name for d in dirs]


def load_tables(rules) -> Optional[Tables]:
    """Tables for `rules` if valid ones exist, else None (never raises)."""
    spec = getattr(rules, "spec", None)
    if spec is None:
        return None
    try:
        from variant.spec import spec_hash
        want = spec_hash(spec)
    except Exception:
        return None
    for d in _candidates(spec.name):
        try:
            meta = json.loads((d / "meta.json").read_text())
            if meta.get("spec_hash") != want or not meta.get("complete", {}).get("equity_random"):
                continue
            table = np.load(d / "classes.npy", allow_pickle=False)
            ci = ClassIndex(rules.deck, int(meta["hole_size"]), table)
            eq = np.load(d / "eq_random.npy", allow_pickle=False)
            rng = None
            if meta.get("complete", {}).get("equity_range") and (d / "eq_range.npy").is_file():
                rng = np.load(d / "eq_range.npy", allow_pickle=False)
            if len(eq) != int(meta["n_classes"]):
                continue
            log(f"loaded precomputed tables from {d}")
            return Tables(meta, ci, eq, rng)
        except Exception as e:  # missing / unreadable / stale: compute live instead
            log(f"no usable tables in {d}: {e!r}")
    return None
