"""Hyperparameter loading: built-in defaults <- bot/embedded.PARAMS[name] <- explicit overrides.

The bot cannot read files at run time, so the shipped values (bot/config/*.json) are embedded
into bot/embedded.py by tools/embed_data.py. A missing or broken embedded entry means defaults,
so the bot always starts. Unknown keys are ignored with a warning.
"""
from __future__ import annotations

from typing import Any, Optional

from bot.log import warn


def load_params(name: str, defaults: dict[str, Any], overrides: Optional[dict] = None) -> dict[str, Any]:
    params = dict(defaults)
    try:
        from bot import embedded                 # looked up per call so tests can swap PARAMS
        _merge(params, embedded.PARAMS.get(name, {}), f"embedded {name}")
    except Exception as e:                        # broken module: run on defaults
        warn(f"could not use embedded params for {name}: {e!r}; using defaults")
    if overrides:
        _merge(params, overrides, "overrides")
    return params


def _merge(params: dict, data: Any, source: str) -> None:
    if not isinstance(data, dict):
        warn(f"{source}: expected a JSON object")
        return
    for k, v in data.items():
        if k.startswith("_"):
            continue  # comments
        if k not in params:
            warn(f"{source}: unknown parameter {k!r} ignored")
            continue
        params[k] = v


def per_street(values: Any, street: int) -> float:
    """Pick a per-street value; lists shorter than the street count repeat their last entry
    (so configs work for variants with more betting rounds)."""
    if isinstance(values, (list, tuple)):
        return float(values[min(street, len(values) - 1)]) if values else 0.0
    return float(values)
