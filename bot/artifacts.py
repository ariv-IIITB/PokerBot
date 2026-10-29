"""Embedded artifacts: precomputed data shipped inside bot/embedded.py (the bot reads no files).

An artifact is {"meta": {...}, "files": {stem: <base64 of a .npy file>}}. meta.json, written by
the offline builder next to the .npy files in data/<variant>/, carries the variant's spec hash
and a "complete" map ({"equity_random": true, ...}). An artifact is used only for the variant
it was built for and only once its required part is complete.

`Layout` says which files make one artifact. tools/embed_data.py packs artifacts with it and the
bot's loaders unpack them with it, so the spec-hash and completeness rules live here once.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class Layout:
    name: str                          # module-level name in bot/embedded.py, e.g. "TABLES"
    need: str                          # meta["complete"] key that must be true to use it at all
    files: dict                        # file stem -> None (required) or the "complete" key it needs


def part_complete(meta: dict, key: str) -> bool:
    return bool(meta.get("complete", {}).get(key))


def usable(meta: dict, spec, layout: Layout) -> bool:
    """meta was built for this exact variant and its required part is complete."""
    from variant.spec import spec_hash
    return meta.get("spec_hash") == spec_hash(spec) and part_complete(meta, layout.need)


def wanted(meta: dict, layout: Layout, stem: str) -> bool:
    """Ship / use this file: it is required, or its optional part is complete."""
    key = layout.files[stem]
    return key is None or part_complete(meta, key)


def encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def decode_array(b64) -> np.ndarray:
    """A .npy file embedded as base64 (a string, or a tuple of line pieces) -> array."""
    text = b64 if isinstance(b64, str) else "".join(b64)
    return np.lib.format.read_array(io.BytesIO(base64.b64decode(text)), allow_pickle=False)


def unpack(layout: Layout, spec, artifact) -> Optional[tuple[dict, dict]]:
    """(meta, {stem: array}) if `artifact` is usable for `spec`, else None. Missing optional
    files are left out; a missing required file raises KeyError (callers treat it as unusable)."""
    if not artifact:
        return None
    meta, files = artifact["meta"], artifact["files"]
    if not usable(meta, spec, layout):
        return None
    arrays = {s: decode_array(files[s]) for s in layout.files
              if wanted(meta, layout, s) and (layout.files[s] is None or s in files)}
    return meta, arrays
