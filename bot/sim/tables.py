"""Optional precomputed data (built offline by lab/precompute.py), embedded in the bot.

The bot cannot read files at run time, so tools/embed_data.py writes the tables into
bot/embedded.py as the "tables" artifact (bot/artifacts.py: the .npy files as base64 plus
meta.json). A table is used only if it was built for the active variant and is complete
(`ready`); anything missing, unreadable or mismatched means "no tables" and the bot computes
live instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from bot.artifacts import _UNSET, decode_npy, embedded
from bot.log import log
from bot.sim.canonical import ClassIndex

REQUIRED = ("classes", "eq_random")          # files the "tables" artifact must have
OPTIONAL = ("eq_range",)                     # used only when meta says it is complete


@dataclass
class Tables:
    meta: dict
    classes: ClassIndex
    eq_random: np.ndarray                 # per class: share vs a random hand from the start
    eq_range: Optional[np.ndarray] = None # per class: share vs the top-X% range

    def start_share(self, hole) -> float:
        return float(self.eq_random[self.classes.class_of(hole)])


def ready(meta: dict, name: str = "eq_random") -> bool:
    """Is table file `name` complete according to meta.json? (shared with tools/embed_data.py)"""
    key = {"eq_random": "equity_random", "eq_range": "equity_range"}.get(name)
    return key is None or bool(meta.get("complete", {}).get(key))


def load_tables(rules, embedded_tables=_UNSET) -> Optional[Tables]:
    """Tables for `rules` if valid ones are embedded, else None (never raises).
    `embedded_tables` is the "tables" artifact; default bot.embedded.ARTIFACTS["tables"]."""
    try:
        art = embedded("tables", rules, embedded_tables)
        if art is None or not ready(art["meta"]):
            return None
        meta, files = art["meta"], art["files"]
        ci = ClassIndex(rules.deck, int(meta["hole_size"]), decode_npy(files["classes"]))
        eq = decode_npy(files["eq_random"])
        rng = decode_npy(files["eq_range"]) if "eq_range" in files and ready(meta, "eq_range") else None
        if len(eq) != int(meta["n_classes"]):
            return None
        log(f"loaded embedded tables for {rules.spec.name} ({len(eq)} classes)")
        return Tables(meta, ci, eq, rng)
    except Exception as e:  # missing / unreadable / stale: compute live instead
        log(f"no usable embedded tables: {e!r}")
        return None
