"""Precomputed artifacts embedded in the bot (the bot reads no files at run time).

tools/embed_data.py writes `ARTIFACTS` into bot/embedded.py: {name: {"meta": {...}, "files":
{file: base64 of a .npy}}}. Each artifact's meta carries the spec hash of the variant it was
built for; an artifact for another variant is never used. Today: "tables" (bot/sim/tables.py).
The producer (tools/embed_data.py) and the consumers share this module, so the encoding and the
staleness rule live in one place.
"""
from __future__ import annotations

import base64
import io
from typing import Optional

import numpy as np

_UNSET = object()


def encode_npy(raw: bytes) -> str:
    """A .npy file's bytes -> the base64 text stored in bot/embedded.py."""
    return base64.b64encode(raw).decode("ascii")


def decode_npy(b64) -> np.ndarray:
    """Embedded base64 (a string, or a tuple of line pieces) -> array."""
    text = b64 if isinstance(b64, str) else "".join(b64)
    return np.lib.format.read_array(io.BytesIO(base64.b64decode(text)), allow_pickle=False)


def built_for(meta, spec) -> bool:
    """True if an artifact's meta says it was built for exactly this variant spec."""
    from variant.spec import spec_hash
    return isinstance(meta, dict) and meta.get("spec_hash") == spec_hash(spec)


def embedded(name: str, rules, source=_UNSET) -> Optional[dict]:
    """The embedded artifact `name` ({"meta", "files"}) if it was built for `rules`' variant,
    else None. `source` is the artifact itself (tests and tools pass their own); the default is
    bot.embedded.ARTIFACTS[name]. Raises nothing for a missing artifact; callers still guard
    decoding, which can fail on corrupt data."""
    spec = getattr(rules, "spec", None)
    if spec is None:
        return None
    if source is _UNSET:
        from bot import embedded as emb
        source = (getattr(emb, "ARTIFACTS", None) or {}).get(name)
    if not isinstance(source, dict) or not built_for(source.get("meta"), spec):
        return None
    return source
