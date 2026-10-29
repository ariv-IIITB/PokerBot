"""CFR brain (lab only): plays a precomputed MCCFR-lite betting strategy, falling back to
Tier 2. Not part of the submitted bot: CFR is a no-go (see "CFR status" in
docs/PART3_ROADMAP.md), so this lives in lab/, is registered only in lab/players.py, and is
never packaged. Run it with `lab.harness tier2 cfr` or `lab.run_brain cfr`.

At a betting decision it rebuilds the hand (bot/sim), maps the hand's betting so far onto
the abstraction (a raise the abstraction could have made gets exactly its training label;
other sizes use the pseudo-harmonic mapping, bot/abstraction.py), looks up (street,
hand-strength bucket, abstract history) in the strategy table and samples an abstract
action. The runtime key equals the trainer's key (tests/test_cfr_runtime.py). Outside the
table (or for any non-betting decision, or when the table is missing or for another
variant) it plays exactly like Tier 2, endgame lock included.
Strategy file: data/<variant>/cfr_strategy.json (lab/cfr/train.py), loaded read-only; the
`strategy_file` parameter points at another file (lab experiments). `stats` counts how
each betting decision was made (table hit, off-tree, endgame lock, ...).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from bot.actions import Action, LegalActions
from bot.brains.tier2 import Tier2Brain
from bot.log import log
from bot.abstraction import Bucketer, abstract_actions, extend_history, infoset_key, observed_label
from bot.state import GameState

ROOT = Path(__file__).resolve().parents[2]


def _candidates(name: str) -> list[Path]:
    """Where a lab-only data file for variant `name` may live ($POKERBOT_DATA, then data/)."""
    dirs = [Path(os.environ["POKERBOT_DATA"])] if os.environ.get("POKERBOT_DATA") else []
    return [d / name for d in dirs + [ROOT / "data"]]


class CFRBrain(Tier2Brain):
    name = "cfr"
    param_file = "cfr"

    def __init__(self, config: Optional[dict] = None, **kw) -> None:
        super().__init__(config, **kw)
        self.strategy: Optional[dict] = None
        self.bucketer: Optional[Bucketer] = None
        self.fractions: Optional[dict] = None    # raise sizes of the trained abstraction
        self.hits = self.misses = 0
        # Why betting decisions did / didn't use the table (diagnostics, lab reports).
        self.stats = {"lock": 0, "no_rec": 0, "hit": 0, "miss_key": 0, "miss_len": 0,
                      "translated": 0}
        self.on_rules()

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        d = Tier2Brain.defaults()
        d["strategy_file"] = ""        # explicit strategy JSON (lab experiments); "" = search
        return d

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
            explicit = self.p.get("strategy_file")
            files = ([Path(explicit)] if explicit
                     else [d / "cfr_strategy.json" for d in _candidates(spec.name)])
            for f in files:
                if f.is_file():
                    doc = json.loads(f.read_text())
                    if doc.get("spec_hash") == want:
                        log(f"CFR strategy: {len(doc['table'])} infosets from {f}")
                        self.fractions = doc.get("fractions")
                        return doc["table"], Bucketer(self.rules, int(doc["buckets"]))
        except Exception as e:
            log(f"no CFR strategy: {e!r}")
        return None, None

    def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
        h = state.hand
        if self.strategy is None or legal.can_special or h is None or not h.hole:
            return super().decide(state, legal, budget_s)
        if self.situation(state).locked():                  # Tier 2's own rule and params
            self.stats["lock"] += 1
            return super().decide(state, legal, budget_s)
        found = self.table_key(state, legal)
        if found is None:
            self.stats["no_rec"] += 1
            return super().decide(state, legal, budget_s)
        key, acts, translated = found
        probs = self.strategy.get(key)
        self.stats["translated"] += int(translated)
        if probs is None or len(probs) != len(acts):
            self.misses += 1
            self.stats["miss_key" if probs is None else "miss_len"] += 1
            return super().decide(state, legal, budget_s)
        self.hits += 1
        self.stats["hit"] += 1
        # Tables hold uint8 weights summing to 255, or floats (lab exports): sample by weight.
        r = self.rng.random() * sum(probs)
        cum = 0.0
        for (label, action), w in zip(acts, probs):
            cum += w
            if r < cum:
                return action
        return acts[-1][1]

    def table_key(self, state: GameState, legal: LegalActions):
        """(infoset key, abstract actions, opponent-bet-translated?) for this decision, as
        the trainer (lab/cfr/abstract_game.py) would see it; None if the hand can't be
        rebuilt. The key is (street, bucket of our real cards, abstract betting history)."""
        h = state.hand
        rec = self.situation(state).rec                    # shared with the Tier 2 fallback
        if rec is None or h is None:
            return None
        fr = self.fractions
        hist, translated = "", False
        log = rec.bet_log
        for i, (p, a, pot, call, bet, all_in, st_street, was_legal) in enumerate(log):
            label, moved = observed_label(a, was_legal, pot, call, bet, all_in, self.rng, fr)
            translated |= moved and p != rec.me
            after = log[i + 1][6] if i + 1 < len(log) else rec.state.street
            hist = extend_history(hist, label, st_street, after)
        real = [rec.mapping.get(t, t) for t in rec.state.hole[rec.me]]
        board = [rec.mapping.get(t, t) for t in rec.state.board]
        key = infoset_key(rec.state.street, self.bucketer.bucket(real, board), hist)
        acts = abstract_actions(legal, h.pot, h.tocall, h.my_bet or 0, fr)
        return key, acts, translated
