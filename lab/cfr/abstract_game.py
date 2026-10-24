"""The active variant as an abstract game for MCCFR, using bot/game for the rules.

State = (GameState, history string). Betting decisions offer the abstract actions of
bot/sim/abstraction.py; non-betting decisions (card steps, bids, ...) are resolved
automatically with the first legal option (an abstraction limitation: MCCFR here learns
betting only). The infoset is (street, hand-strength bucket, betting history this hand).
"""
from __future__ import annotations


from bot.actions import Action
from bot.game.runner import act, advance, legal_actions
from bot.game.state import GameState
from bot.sim.abstraction import Bucketer, abstract_actions, infoset_key


class AbstractGame:
    def __init__(self, rules, n_buckets: int = 8) -> None:
        self.rules = rules
        self.bucketer = Bucketer(rules, n_buckets)

    def _settle(self, st):
        """Advance through automatic steps and non-betting decisions."""
        while True:
            p = advance(st)
            if p is None:
                return None
            legal = legal_actions(st, p)
            if legal.can_special:
                act(st, p, Action.special(legal.special.default()))
                continue
            return p

    def root(self, rng):
        deck = [self.rules.deck[i] for i in rng.permutation(len(self.rules.deck))]
        st = GameState(self.rules, deck, [self.rules.starting_stack] * 2, record=False)
        self._settle(st)
        return (st, "")

    def is_terminal(self, s) -> bool:
        return s[0].done

    def utility(self, s, p: int) -> float:
        return float(s[0].deltas[p])

    def to_act(self, s):
        st = s[0]
        return st.rules.program[st.pc].next_actor(st)

    def chance(self, s, rng):
        return s

    def _abstract(self, s):
        st = s[0]
        p = self.to_act(s)
        legal = legal_actions(st, p)
        return abstract_actions(legal, st.pot, st.to_call(p), st.bet[p])

    def actions(self, s):
        return [label for label, _ in self._abstract(s)]

    def play(self, s, label):
        st, hist = s
        concrete = dict(self._abstract(s))[label]
        g = st.copy()
        p = self.to_act(s)
        act(g, p, concrete)
        self._settle(g)
        sep = "/" if g.street != st.street else ""
        return (g, hist + label + sep)

    def infoset(self, s, p: int):
        st, hist = s
        return infoset_key(st.street, self.bucketer.bucket(st.hole[p], st.board), hist)
