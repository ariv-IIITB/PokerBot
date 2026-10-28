"""
opponent_model.py - Online Bayesian opponent tracker and range weight updater.
"""

from typing import List, Tuple
import numpy as np
from preflop import TOTAL_COMBOS


class BetaTracker:
    def __init__(self, prior_alpha: float = 6.0, prior_beta: float = 6.0):
        self.alpha_0 = prior_alpha
        self.beta_0 = prior_beta
        self.successes = 0.0
        self.trials = 0.0

    def observe(self, success: bool, weight: float = 1.0) -> None:
        self.trials += weight
        if success:
            self.successes += weight

    @property
    def mean(self) -> float:
        return (self.alpha_0 + self.successes) / (self.alpha_0 + self.beta_0 + self.trials)


class OpponentModel:
    def __init__(self) -> None:
        self.vpip = BetaTracker(10.0, 4.0)
        self.pfr = BetaTracker(8.0, 5.0)
        self.fold_to_3bet = BetaTracker(6.0, 6.0)
        self.cbet_flop = BetaTracker(7.0, 5.0)
        self.fold_to_cbet = BetaTracker(5.0, 7.0)
        self.river_bet = BetaTracker(5.0, 6.0)
        self.fold_to_river = BetaTracker(5.0, 5.0)
        self.shove_freq = BetaTracker(1.0, 19.0)
        self.sizing_history: List[Tuple[float, float]] = []

    def observe_preflop_action(
        self, is_vpip: bool, is_pfr: bool, faced_3bet: bool = False, folded_3bet: bool = False
    ) -> None:
        self.vpip.observe(is_vpip)
        self.pfr.observe(is_pfr)
        if faced_3bet:
            self.fold_to_3bet.observe(folded_3bet)

    def observe_cbet(self, did_cbet: bool) -> None:
        self.cbet_flop.observe(did_cbet)

    def observe_fold_to_cbet(self, did_fold: bool) -> None:
        self.fold_to_cbet.observe(did_fold)

    def observe_river_action(self, did_bet: bool, faced_bet: bool = False, did_fold: bool = False) -> None:
        self.river_bet.observe(did_bet)
        if faced_bet:
            self.fold_to_river.observe(did_fold)

    def observe_shove(self, did_shove: bool) -> None:
        self.shove_freq.observe(did_shove)

    def record_showdown(self, bet_pot_ratio: float, true_strength: float) -> None:
        self.sizing_history.append((bet_pot_ratio, true_strength))

    def get_initial_villain_weights(self) -> np.ndarray:
        return np.ones(TOTAL_COMBOS, dtype=np.float64)
