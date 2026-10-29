"""Optional precomputed data (built offline by lab/precompute.py), embedded in the bot.

The bot cannot read files at run time, so tools/embed_data.py writes the tables into
bot/embedded.py (TABLES, an artifact in the bot/artifacts.py format). A table is used only if
meta's spec hash matches the active variant's; anything missing, unreadable or mismatched
means "no tables" and the bot computes live instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from bot.artifacts import Layout, unpack
from bot.log import log
from bot.sim.canonical import ClassIndex

# What one TABLES artifact holds (tools/embed_data.py packs it with the same layout).
TABLES = Layout("TABLES", need="equity_random",
                files={"classes": None, "eq_random": None, "eq_range": "equity_range"})

_UNSET = object()


@dataclass
class Tables:
    meta: dict
    classes: ClassIndex
    eq_random: np.ndarray                 # per class: share vs a random hand from the start
    eq_range: Optional[np.ndarray] = None # per class: share vs the top-X% range

    def start_share(self, hole) -> float:
        return float(self.eq_random[self.classes.class_of(hole)])


def load_tables(rules, embedded_tables=_UNSET) -> Optional[Tables]:
    """Tables for `rules` if valid ones are embedded, else None (never raises).
    `embedded_tables` defaults to bot.embedded.TABLES (tests and tools pass their own)."""
    spec = getattr(rules, "spec", None)
    if spec is None:
        return None
    try:
        if embedded_tables is _UNSET:
            from bot import embedded
            embedded_tables = embedded.TABLES
        got = unpack(TABLES, spec, embedded_tables)
        if got is None:
            return None
        meta, arrays = got
        ci = ClassIndex(rules.deck, int(meta["hole_size"]), arrays["classes"])
        eq, rng = arrays["eq_random"], arrays.get("eq_range")
        if len(eq) != int(meta["n_classes"]):
            return None
        log(f"loaded embedded tables for {spec.name} ({len(eq)} classes)")
        return Tables(meta, ci, eq, rng)
    except Exception as e:  # missing / unreadable / stale: compute live instead
        log(f"no usable embedded tables: {e!r}")
        return None
