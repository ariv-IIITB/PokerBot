"""Tier 4 with a blueprint file (lab only): the bot itself may not read files, so the lab hands
the table in. Registered in lab/players.py as "tier4lab":

    .venv/bin/python -m lab.eval 'tier4lab:{"blueprint_file": "data/cfr/run1/blueprint_v1.npz",
        "cfr_streets": [0, 1]}' --pool tier3 --pairs 100 --variant discard_holdem
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np

from bot.brains.tier4 import Tier4Brain
from bot.cfr.blueprint import Blueprint

ROOT = Path(__file__).resolve().parents[3]
_CACHE: dict[str, Blueprint] = {}


def load_blueprint(path: str) -> Blueprint:
    p = Path(path) if Path(path).is_absolute() else ROOT / path
    key = str(p.resolve())
    if key not in _CACHE:
        with np.load(p) as data:
            _CACHE[key] = Blueprint.from_npz(data)
    return _CACHE[key]


class Tier4LabBrain(Tier4Brain):
    name = "tier4lab"
    param_file = "tier4"

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        d = Tier4Brain.defaults()
        d["blueprint_file"] = "data/cfr/run1/blueprint_v1.npz"
        return d

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)
        self.set_blueprint(load_blueprint(str(self.p["blueprint_file"])))
