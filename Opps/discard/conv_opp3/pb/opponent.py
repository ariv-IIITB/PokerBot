"""Opponent model: smoothed (Bayesian-prior) frequency counters for the current match.

Every Rate starts at a balanced-player prior worth `strength` pseudo-observations,
so early reads never swing wildly. Stats reset per match (new Brain per match).
"""


class Rate:
    __slots__ = ("hits", "n", "prior", "strength")

    def __init__(self, prior, strength=10.0):
        self.hits = 0
        self.n = 0
        self.prior = prior
        self.strength = strength

    def add(self, hit):
        self.n += 1
        if hit:
            self.hits += 1

    @property
    def value(self):
        return (self.hits + self.prior * self.strength) / (self.n + self.strength)


class OppModel:
    def __init__(self):
        # --- preflop ---
        self.pf_open = Rate(0.60, 10)          # opp as SB: raises (vs limp/fold)
        self.pf_defend = Rate(0.55, 10)        # opp as BB: continues vs our open
        self.pf_3bet = Rate(0.12, 10)          # opp reraises our open
        self.pf_fold_to_open = Rate(0.40, 10)  # opp folds to our open-raise
        self.pf_fold_to_3bet = Rate(0.45, 8)   # opp folds to our 3-bet
        # --- postflop ---
        self.bet = Rate(0.40, 12)              # opp bets when it has the option
        self.fold_to_bet = Rate(0.40, 12)      # opp folds to our postflop bet
        self.fold_to_raise = Rate(0.45, 8)     # opp folds to our raise over its bet
        self.river_bluff = Rate(0.25, 8)       # opp's river bets/raises shown down weak
        self.hands = 0

    # ---- derived knobs used by ranges / strategy ----
    def agg_scale(self):
        """>1 means opponent bets tighter than average (narrower ranges)."""
        a = self.bet.value
        return min(1.3, max(0.55, 1.4 - 1.5 * (a - 0.2)))

    def bluff_mass(self):
        return 0.03 + 0.25 * self.river_bluff.value

    def bluffiness(self):
        """0..1: how likely opp's aggression is a bluff (drives lighter calldowns)."""
        return min(1.0, max(0.0, (self.river_bluff.value - 0.15) / 0.45))

    def stationness(self):
        """0..1: calls too much / folds too little."""
        return min(1.0, max(0.0, (0.45 - self.fold_to_bet.value) / 0.30))

    def folds_a_lot(self):
        return self.fold_to_bet.value
