"""Phase 23: the CFR brain's runtime infoset key equals the trainer's key.

Hands are played through the lab engine; both players only use abstract actions. At each of
the probe's decisions we compute the key the trainer (AbstractGame) would use from the
engine's true game state, and the key the bot computes from what it saw over the protocol.
They must match: same street, same bucket of the same cards, same abstract history, and
the same abstract action list (labels and amounts).
"""
import numpy as np
import pytest

from lab.cfr.brain import CFRBrain
from bot.game.compile import compile_spec
from bot.protocol import MatchInfo
from lab.cfr.abstraction import Bucketer, abstract_actions, infoset_key
from lab.cfr.abstract_game import AbstractGame
from lab.engine import Hand, Seat, deck_for
from lab.players import InProcessPlayer
from variant.spec import load_catalog


class ProbeBrain(CFRBrain):
    """Records its table key, then plays a random abstract action."""

    def decide(self, state, legal, budget_s):
        found = self.table_key(state, legal)
        self.records.append(found)
        _, acts, _ = found
        return acts[int(self.rng.integers(len(acts)))][1]


class RandomAbstract(CFRBrain):
    def decide(self, state, legal, budget_s):
        h = state.hand
        acts = abstract_actions(legal, h.pot, h.tocall, h.my_bet or 0, self.fractions)
        return acts[int(self.rng.integers(len(acts)))][1]


class TrainerView:
    """Wraps a player; before each decision, computes the trainer's key from the engine."""

    def __init__(self, inner, game, labels, check: bool) -> None:
        self.inner, self.game, self.labels, self.check = inner, game, labels, check
        self.hand = None
        self.role = 0
        self.compared = 0

    def notify(self, msg):
        self.inner.notify(msg)

    def act(self, req):
        st = self.hand.st
        hist, last = "", 0
        for street, label in self.labels:
            if street != last:
                hist += "/"
                last = street
            hist += label
        if self.labels and st.street != last:
            hist += "/"
        acts = self.game._abstract((st, hist))
        action = self.inner.act(req)
        if self.check:
            key = infoset_key(st.street, self.game.bucketer.bucket(st.hole[self.role], st.board), hist)
            got_key, got_acts, _ = self.inner.bot.brain.records[-1]
            assert got_key == key, (got_key, key)
            assert [(l, a.kind, a.amount) for l, a in got_acts] == \
                   [(l, a.kind, a.amount) for l, a in acts]
            self.compared += 1
        label = next(l for l, a in acts if a.kind == action.kind and a.amount == action.amount)
        self.labels.append((st.street, label))
        return action

    def close(self):
        pass


def _setup(name: str, fractions=None):
    spec = load_catalog()[name]
    rules = compile_spec(spec)
    game = AbstractGame(rules, 8, fractions)
    cfg = {"lock_enabled": False, "rollout_worlds": 8, "pimc_worlds": 2, "inference": False}
    brains = [ProbeBrain(cfg, game=spec), RandomAbstract(dict(cfg, seed=7), game=spec)]
    for b in brains:
        b.strategy, b.bucketer, b.fractions = {}, Bucketer(rules, 8), fractions
        b.records = []
    return spec, rules, game, brains


@pytest.mark.parametrize("name,fractions", [("holdem_nl", None),
                                            ("holdem_short30", {"P": 1.0}),
                                            ("raise_cap_deep", None)])
def test_runtime_key_equals_training_key(name, fractions) -> None:
    spec, rules, game, brains = _setup(name, fractions)
    labels: list = []
    probe = TrainerView(InProcessPlayer(brains[0]), game, labels, check=True)
    other = TrainerView(InProcessPlayer(brains[1]), game, labels, check=False)
    info = MatchInfo(150, 60.0, rules.small_blind, rules.big_blind, rules.starting_stack)
    for p in (probe, other):
        p.notify(info)
    for h in range(150):
        labels.clear()
        seats = [Seat(probe, 60.0), Seat(other, 60.0)] if h % 2 == 0 else [Seat(other, 60.0), Seat(probe, 60.0)]
        hand = Hand(spec, seats, [rules.starting_stack] * 2, deck_for(5, h, rules.deck), h, None,
                    rules=rules, rng=np.random.default_rng([5, h]))
        probe.hand = other.hand = hand
        probe.role, other.role = (0, 1) if h % 2 == 0 else (1, 0)
        hand.play()
    assert probe.compared > 100
