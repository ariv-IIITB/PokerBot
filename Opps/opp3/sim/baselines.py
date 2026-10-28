"""Simple baseline bots for the match runner. All share the Brain-style interface:
new_match(total_hands, bank), new_hand(hand_no, hole, button), act(obs), hand_over(result)."""
import random

import numpy as np

from pb.equity import equity
from pb.ranges import pf_percentile
from pb.types import CALL, CHECK, FOLD, RAISE


class BaseBot:
    name = "base"

    def __init__(self, seed=1):
        self.rng = random.Random(seed)
        self.nprng = np.random.default_rng(seed)

    def new_match(self, total_hands=400, bank_per_400=60.0):
        pass

    def new_hand(self, hand_no, hole, button):
        pass

    def hand_over(self, result):
        pass

    def act(self, obs):
        raise NotImplementedError

    # helpers
    @staticmethod
    def passive(obs):
        return (CHECK,) if obs.can_check else (CALL,)

    @staticmethod
    def pot_raise(obs, frac):
        if not obs.can_raise:
            return BaseBot.passive(obs)
        t = int(obs.opp_pip + frac * (obs.pot + obs.to_call))
        return (RAISE, max(obs.min_raise, min(obs.max_raise, t)))

    def eq_random(self, obs, n=150):
        return equity(obs.hole, obs.board, None, n, self.nprng)[0]


class RandomBot(BaseBot):
    name = "random"

    def act(self, obs):
        r = self.rng.random()
        if obs.to_call > 0 and r < 0.15:
            return (FOLD,)
        if r < 0.70:
            return self.passive(obs)
        if obs.can_raise:
            return (RAISE, self.rng.randint(obs.min_raise, obs.max_raise))
        return self.passive(obs)


class CallBot(BaseBot):
    name = "call"

    def act(self, obs):
        return self.passive(obs)


class FoldBot(BaseBot):
    name = "fold"

    def act(self, obs):
        return (CHECK,) if obs.can_check else (FOLD,)


class ShoveBot(BaseBot):
    name = "shove"

    def act(self, obs):
        return (RAISE, obs.max_raise) if obs.can_raise else self.passive(obs)


class ManiacBot(BaseBot):
    name = "maniac"

    def act(self, obs):
        return self.pot_raise(obs, 1.0)


class TagBot(BaseBot):
    """Tight-aggressive: equity vs a random hand, value bets strong, calls with pot odds."""
    name = "tag"

    def __init__(self, seed=1, bet_thr=0.62, call_margin=0.06, open_cut=0.35):
        super().__init__(seed)
        self.bet_thr, self.call_margin, self.open_cut = bet_thr, call_margin, open_cut

    def new_hand(self, hand_no, hole, button):
        self.s = pf_percentile(hole)

    def act(self, obs):
        if obs.street == 0:
            if obs.to_call > 0 and obs.opp_pip <= obs.big_blind:      # SB first to act
                if self.s >= self.open_cut:
                    return self.pot_raise(obs, 1.0)
                return (CALL,) if self.s > 0.2 else (FOLD,)
            if obs.to_call == 0:                                         # BB option
                return self.pot_raise(obs, 1.0) if self.s > 0.6 else (CHECK,)
            req = obs.to_call / float(obs.pot + obs.to_call)
            if self.s > 0.85 and obs.can_raise:
                return self.pot_raise(obs, 1.0)
            return (CALL,) if self.s > max(0.45, req + 0.3) else (FOLD,)
        eq = self.eq_random(obs)
        if obs.to_call > 0:
            req = obs.to_call / float(obs.pot + obs.to_call)
            if eq > 0.80 and obs.can_raise:
                return self.pot_raise(obs, 0.8)
            return (CALL,) if eq > req + self.call_margin else (FOLD,)
        if eq > self.bet_thr:
            return self.pot_raise(obs, 0.66)
        return (CHECK,)


class NitBot(TagBot):
    name = "nit"

    def __init__(self, seed=1):
        super().__init__(seed, bet_thr=0.75, call_margin=0.12, open_cut=0.60)


class LagBot(BaseBot):
    """Loose-aggressive: opens wide, bets a lot, bluffs when checked to."""
    name = "lag"

    def new_hand(self, hand_no, hole, button):
        self.s = pf_percentile(hole)

    def act(self, obs):
        if obs.street == 0:
            if obs.to_call > 0 and obs.opp_pip <= obs.big_blind:
                return self.pot_raise(obs, 1.0) if self.s > 0.15 else (FOLD,)
            if obs.to_call == 0:
                return self.pot_raise(obs, 1.0) if self.s > 0.4 else (CHECK,)
            req = obs.to_call / float(obs.pot + obs.to_call)
            return (CALL,) if self.s > req + 0.1 else (FOLD,)
        eq = self.eq_random(obs)
        if obs.to_call > 0:
            req = obs.to_call / float(obs.pot + obs.to_call)
            if eq > 0.7 and obs.can_raise:
                return self.pot_raise(obs, 1.0)
            return (CALL,) if eq > req - 0.02 else (FOLD,)
        if eq > 0.5 or self.rng.random() < 0.35:
            return self.pot_raise(obs, 0.75)
        return (CHECK,)


class StationBot(BaseBot):
    """Calling station: calls almost anything, raises only monsters."""
    name = "station"

    def act(self, obs):
        if obs.street == 0:
            return self.passive(obs)
        eq = self.eq_random(obs)
        if obs.to_call > 0:
            if eq > 0.85 and obs.can_raise:
                return self.pot_raise(obs, 0.7)
            return (CALL,) if eq > 0.30 else (FOLD,)
        return self.pot_raise(obs, 0.5) if eq > 0.8 else (CHECK,)


REGISTRY = {
    "random": RandomBot, "call": CallBot, "fold": FoldBot, "shove": ShoveBot,
    "maniac": ManiacBot, "tag": TagBot, "nit": NitBot, "lag": LagBot, "station": StationBot,
}
