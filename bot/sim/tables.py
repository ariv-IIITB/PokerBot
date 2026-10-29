"""Optional precomputed data (built offline by lab/precompute.py), embedded in the bot.

The bot cannot read files at run time, so tools/embed_data.py writes the tables into
bot/embedded.py (TABLES: the .npy files as base64 plus meta.json). A table is used only if
meta's spec hash matches the active variant's; anything missing, unreadable or mismatched
means "no tables" and the bot computes live instead.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Optional

import numpy as np

from bot.log import log
from bot.sim.canonical import ClassIndex

_UNSET = object()


@dataclass
class Tables:
    meta: dict
    classes: ClassIndex
    eq_random: np.ndarray                 # per class: share vs a random hand from the start
    eq_range: Optional[np.ndarray] = None # per class: share vs the top-X% range

    def start_share(self, hole) -> float:
        return float(self.eq_random[self.classes.class_of(hole)])


def _array(b64) -> np.ndarray:
    """A .npy file embedded as base64 (a string, or a tuple of line pieces) -> array."""
    text = b64 if isinstance(b64, str) else "".join(b64)
    return np.lib.format.read_array(io.BytesIO(base64.b64decode(text)), allow_pickle=False)


def load_tables(rules, embedded_tables=_UNSET) -> Optional[Tables]:
    """Tables for `rules` if valid ones are embedded, else None (never raises).
    `embedded_tables` defaults to bot.embedded.TABLES (tests and tools pass their own)."""
    spec = getattr(rules, "spec", None)
    if spec is None:
        return None
    try:
        from variant.spec import spec_hash
        want = spec_hash(spec)
        if embedded_tables is _UNSET:
            from bot import embedded
            embedded_tables = embedded.TABLES
        if not embedded_tables:
            return None
        meta, files = embedded_tables["meta"], embedded_tables["files"]
        if meta.get("spec_hash") != want or not meta.get("complete", {}).get("equity_random"):
            return None
        ci = ClassIndex(rules.deck, int(meta["hole_size"]), _array(files["classes"]))
        eq = _array(files["eq_random"])
        rng = _array(files["eq_range"]) if "eq_range" in files and \
            meta.get("complete", {}).get("equity_range") else None
        if len(eq) != int(meta["n_classes"]):
            return None
        log(f"loaded embedded tables for {spec.name} ({len(eq)} classes)")
        return Tables(meta, ci, eq, rng)
    except Exception as e:  # missing / unreadable / stale: compute live instead
        log(f"no usable embedded tables: {e!r}")
        return None
