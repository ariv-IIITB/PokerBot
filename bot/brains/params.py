"""Hyperparameter loading: built-in defaults <- bot/config/<name>.json <- explicit overrides.

The JSON file is optional (read-only access; missing or broken file = defaults), so the
bot always starts even if data files aren't shipped. Unknown keys are ignored with a warning.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from bot.log import warn

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_params(name: str, defaults: dict[str, Any], overrides: Optional[dict] = None,
                config_dir: Optional[Path] = None) -> dict[str, Any]:
    params = dict(defaults)
    path = (config_dir or CONFIG_DIR) / f"{name}.json"
    try:
        with open(path, "r", encoding="utf-8") as f:  # sandbox-allow: bot/config/*.json, embedded in Phase D
            _merge(params, json.load(f), str(path))
    except FileNotFoundError:
        pass
    except Exception as e:  # unreadable / invalid JSON: run on defaults
        warn(f"could not read {path}: {e!r}; using defaults")
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
