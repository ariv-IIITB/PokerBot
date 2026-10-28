"""Time-bank manager: decides how long each decision may think.

Tournament budget is ~60 s for 400 hands (0.15 s/hand). We deliberately target
well under that and keep a reserve for engine/IO overhead, because the engine's
clock includes process communication time we cannot measure.
"""
import time

STREET_WEIGHT = (0.20, 0.35, 0.30, 0.35)     # share of the per-hand budget (sums >1: not every hand reaches later streets)


class Clock:
    def __init__(self, total_hands=400, bank_per_400=60.0):
        self.total_hands = total_hands
        self.initial_bank = bank_per_400 * total_hands / 400.0
        self.used = 0.0                      # our own measured thinking time
        self.cost_per_sample = 1.2e-5        # EMA of seconds per MC sample (adaptive)
        self.reserve = max(1.5, 0.10 * self.initial_bank)

    def remaining(self, time_left):
        """Best estimate of bank left: engine value if given, else our own accounting."""
        if time_left is not None:
            return float(time_left)
        return self.initial_bank - self.used

    def mode(self, time_left, hands_left):
        """'full' | 'lean' | 'panic'."""
        rem = self.remaining(time_left)
        if rem < 0.8 + 0.004 * hands_left:
            return "panic"
        per = (rem - self.reserve) / max(hands_left, 1)
        if per < 0.02:
            return "lean"
        return "full"

    def budget(self, time_left, hands_left, street):
        """Seconds this decision may spend on Monte-Carlo."""
        rem = self.remaining(time_left)
        per_hand = max(0.0, rem - self.reserve) / max(hands_left, 1)
        b = per_hand * STREET_WEIGHT[min(max(street, 0), 3)] * 1.2
        return min(b, 0.25)

    def samples(self, budget, lo=80, hi=1500):
        n = int(budget / max(self.cost_per_sample, 1e-7))
        return max(lo, min(hi, n))

    def observe(self, elapsed, n_samples):
        """Update per-sample cost estimate from a measured MC call."""
        if n_samples >= 50:
            c = elapsed / n_samples
            self.cost_per_sample = 0.8 * self.cost_per_sample + 0.2 * c

    def charge(self, elapsed):
        self.used += elapsed


def now():
    return time.perf_counter()
