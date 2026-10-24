"""CFR brain: plays a precomputed MCCFR-lite betting strategy, falling back to Tier 2.

At a betting decision it rebuilds the hand (bot/sim), maps the hand's betting so far onto
the abstraction (pseudo-harmonic mapping for opponent bet sizes, bot/sim/abstraction.py),
looks up (street, hand-strength bucket, abstract history) in the strategy table and samples
an abstract action. Outside the table (or for any non-betting decision, or when the table
is missing or for another variant) it plays exactly like Tier 2, endgame lock included.
Strategy file: data/<variant>/cfr_strategy.json (lab/cfr/train.py), loaded read-only.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from bot.actions import Action, LegalActions
from bot.brains.tier2 import Tier2Brain, lock_margin
from bot.log import log
from bot.sim.abstraction import Bucketer, abstract_actions, infoset_key, raise_label
from bot.sim.tables import _candidates
from bot.state import GameState


class CFRBrain(Tier2Brain):
    name = "cfr"
    param_file = "cfr"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)
        self.strategy: Optional[dict] = None
        self.bucketer: Optional[Bucketer] = None
        self.hits = self.misses = 0
        self.on_rules()

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return Tier2Brain.defaults()

    def on_rules(self) -> None:
        super().on_rules()
        self.strategy, self.bucketer = self._load()

    def _load(self):
        spec = getattr(self.rules, "spec", None)
        if spec is None:
            return None, None
        try:
            from variant.spec import spec_hash
            want = spec_hash(spec)
            for d in _candidates(spec.name):
                f = d / "cfr_strategy.json"
                if f.is_file():
                    doc = json.loads(f.read_text())
                    if doc.get("spec_hash") == want:
                        log(f"CFR strategy: {len(doc['table'])} infosets from {f}")
                        return doc["table"], Bucketer(self.rules, int(doc["buckets"]))
        except Exception as e:
            log(f"no CFR strategy: {e!r}")
        return None, None

    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        h = state.hand
        if (self.strategy is None or legal.can_special or h is None or not h.hole
                or (self.p["lock_enabled"] and (lock_margin(state, True, self.rules) or 0) > 0)):
            return super().decide(state, legal, budget_s)
        rec = self.reconstruct(state)
        if rec is None:
            return super().decide(state, legal, budget_s)
        hist, street = "", 0
        for p, a, pot, call, bet, all_in, st_street in rec.bet_log:
            if st_street != street:
                hist += "/" * (st_street - street) if hist else ""
                street = st_street
            if a.kind == "F":
                hist += "F"
            elif a.kind in ("C", "K"):
                hist += "C"
            else:
                hist += raise_label(a.amount, pot, call, bet, self.rng, all_in)
        if rec.state.street != street and hist:
            hist += "/"
        real = [rec.mapping.get(t, t) for t in rec.state.hole[rec.me]]
        board = [rec.mapping.get(t, t) for t in rec.state.board]
        key = infoset_key(rec.state.street, self.bucketer.bucket(real, board), hist)
        probs = self.strategy.get(key)
        acts = abstract_actions(legal, h.pot, h.tocall, h.my_bet or 0)
        if probs is None or len(probs) != len(acts):
            self.misses += 1
            return super().decide(state, legal, budget_s)
        self.hits += 1
        r = self.rng.integers(255)
        cum = 0
        for (label, action), w in zip(acts, probs):
            cum += w
            if r < cum:
                return action
        return acts[-1][1]
