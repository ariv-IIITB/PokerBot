"""Tier 4: the CFR blueprint on chosen streets, Tier 3 everywhere else (build map C5).

On a betting decision on a street listed in `cfr_streets`, the hand's betting is replayed into the
abstract history (bot/cfr/blueprint.py), our bucket is computed, and an abstract action is sampled
from the blueprint row and turned into chips on the real state. Anything else goes to Tier 3: the
discard, streets not listed, a history the abstraction cannot hold, an untrained row, a real state
that disagrees with the replay, a tight budget, or any error. The endgame lock is handled before
`play` (Tier2Brain.decide). `cfr_streets: []` never consults the blueprint (= Tier 3).

The blueprint is the embedded artifact "blueprint" (tools/embed_data.py); the lab can hand one in
with `set_blueprint` (lab/cfr/fast/brain.py). `stats` counts hits, misses by reason, translations.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from bot.actions import Action, LegalActions, safe_action
from bot.artifacts import embedded
from bot.brains.tier3 import Tier3Brain
from bot.cfr.blueprint import Blueprint, abstract_view, bucket, menu
from bot.log import warn
from bot.situation import Situation

T4_DEFAULTS: dict[str, Any] = {
    "cfr_streets": [0, 1],         # streets played from the blueprint (0 preflop .. 3 river)
    "cfr_min_budget_s": 0.01,      # below this budget, Tier 3 decides (bucket cost ~3 ms on the flop)
}


class Tier4Brain(Tier3Brain):
    name = "tier4"
    param_file = "tier4"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)
        self.blueprint: Optional[Blueprint] = None
        self._bp_loaded = False
        self._bucket_cache: dict = {}
        self.stats.update({"t4_hits": 0, "t4_no_blueprint": 0, "t4_miss_tree": 0, "t4_miss_state": 0,
                           "t4_miss_bucket": 0, "t4_miss_row": 0, "t4_budget": 0, "t4_errors": 0,
                           "t4_translated": 0, "t4_remapped": 0, "t4_lookup_us": 0})

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        d = Tier3Brain.defaults()
        d.update({k: (list(v) if isinstance(v, list) else v) for k, v in T4_DEFAULTS.items()})
        return d

    # ---- the table
    def set_blueprint(self, bp: Optional[Blueprint]) -> None:
        self.blueprint, self._bp_loaded = bp, True

    def _table(self) -> Optional[Blueprint]:
        if not self._bp_loaded:
            self._bp_loaded = True
            try:
                art = embedded("blueprint", self.rules)
                self.blueprint = Blueprint.from_artifact(art) if art is not None else None
            except Exception as e:                       # corrupt artifact: Tier 3 plays
                warn(f"tier4: blueprint not usable: {e!r}")
                self.blueprint = None
        return self.blueprint

    # ---- entry point
    def play(self, s: Situation, legal: LegalActions, budget_s: float, p: dict) -> Action:
        h = s.hand
        if h is None or legal.can_special or h.street not in p.get("cfr_streets", ()):
            return super().play(s, legal, budget_s, p)
        if budget_s < float(p["cfr_min_budget_s"]):
            self.stats["t4_budget"] += 1
            return super().play(s, legal, budget_s, p)
        t0 = time.perf_counter()
        try:
            a = self._from_blueprint(s, legal)
        except Exception as e:                           # never cost a hand: Tier 3 decides
            self.stats["t4_errors"] += 1
            warn(f"tier4 failed: {e!r}")
            a = None
        self.stats["t4_lookup_us"] += int((time.perf_counter() - t0) * 1e6)
        return a if a is not None else super().play(s, legal, budget_s, p)

    def _from_blueprint(self, s: Situation, legal: LegalActions) -> Optional[Action]:
        h = s.hand
        bp = self._table()
        if bp is None:
            self.stats["t4_no_blueprint"] += 1
            return None
        par = bp.params
        view = abstract_view(h, par, self.pyrng)
        if view is None:
            self.stats["t4_miss_tree"] += 1
            return None
        st, seat = view.street, view.seat
        if st.to_call(seat) != h.tocall or st.stacks[seat] != h.my_stack:
            self.stats["t4_miss_state"] += 1             # the replay disagrees with the engine
            return None
        acts = menu(st, seat, par)
        key = (h.hand_id, h.street)
        b = self._bucket_cache.get(key)
        if b is None:
            tables = self.perception.tables
            b = bucket(h, h.street, bp, self.rules.evaluator, tables.classes if tables else None)
            if b is None:
                self.stats["t4_miss_bucket"] += 1
                return None
            self._bucket_cache = {key: b}
        probs = bp.lookup(h.street, view.history, b, len(acts))
        if probs is None:
            self.stats["t4_miss_row"] += 1
            return None
        self.stats["t4_hits"] += 1
        self.stats["t4_translated"] += view.translated
        r = self.pyrng.random() * float(probs.sum())
        i, cum = 0, float(probs[0])
        while r >= cum and i < len(acts) - 1:
            i += 1
            cum += float(probs[i])
        return self._concrete(acts[i], legal)

    def _concrete(self, act: tuple, legal: LegalActions) -> Action:
        label, kind, amt = act
        if kind == "F" and legal.fold:
            return Action.fold()
        if kind == "K" and legal.check:
            return Action.check()
        if kind == "C" and legal.call:
            return Action.call()
        if kind == "R" and legal.can_raise:
            return Action.raise_to(legal.nearest_raise(int(amt)))
        self.stats["t4_remapped"] += 1                   # the engine disagrees: closest safe action
        if kind == "R" and legal.call:
            return Action.call()
        return Action.check() if legal.check else safe_action(legal)
