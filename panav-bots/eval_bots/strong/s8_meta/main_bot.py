"""s8_meta: a Bayesian posterior over opponent archetypes; parameters are the posterior-weighted mix of per-archetype
best-response parameters, on top of the sound equity-vs-range default (common.py)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run  # noqa: E402

# name: (p_bet when checked to, postflop reply to our bet [fold, call, raise], preflop reply to our raise
#        [fold, call, raise], preflop raise rate when not facing a raise)
ARCH = {
    "tightpassive": (0.20, (0.45, 0.47, 0.08), (0.50, 0.42, 0.08), 0.25),
    "station":      (0.20, (0.12, 0.80, 0.08), (0.15, 0.75, 0.10), 0.20),
    "tag":          (0.45, (0.35, 0.50, 0.15), (0.35, 0.45, 0.20), 0.50),
    "maniac":       (0.70, (0.15, 0.45, 0.40), (0.20, 0.35, 0.45), 0.75),
    "overfolder":   (0.35, (0.65, 0.28, 0.07), (0.65, 0.28, 0.07), 0.40),
    "betfold":      (0.55, (0.60, 0.25, 0.15), (0.40, 0.40, 0.20), 0.45),
    "balanced":     (0.40, (0.30, 0.55, 0.15), (0.30, 0.50, 0.20), 0.45),
}
# prior: the sound default (balanced) gets the most mass
PRIOR = {"tightpassive": 1, "station": 1, "tag": 1.5, "maniac": 1, "overfolder": 1, "betfold": 1, "balanced": 3}

# per-archetype best-response changes to BASE (additive on numbers, applied elementwise on tuples)
DELTA = {
    "tightpassive": dict(cbet=0.30, semi=0.20, river_bluff=0.10, margin=0.02, pressure_scale=0.35, open=-0.06),
    "station": dict(cbet=-0.45, semi=-0.25, river_bluff=-0.14, value=(-0.07, -0.07, -0.08), margin=-0.01,
                    three_bluff=-0.10, pressure_scale=-0.2, defend=0.0),
    "tag": dict(),
    "maniac": dict(cbet=-0.1, semi=-0.10, river_bluff=-0.10, raise_val=-0.05, margin=-0.035, pressure_scale=-0.5,
                   value=(-0.04, -0.04, -0.04), defend=-0.06, three=-0.04, call3=-0.08),
    "overfolder": dict(cbet=0.35, semi=0.30, river_bluff=0.25, three_bluff=0.15, open=-0.08, margin=0.01,
                       value=(0.03, 0.03, 0.0)),
    "betfold": dict(cbet=0.15, semi=0.35, river_bluff=0.05, margin=-0.02, pressure_scale=-0.3, defend=-0.03,
                    raise_val=-0.04),
    "balanced": dict(),
}
NAMES = list(ARCH)
TEMPER = 0.7
FORGET = 0.995


def _resp_idx(a):
    return 0 if a == "fold" else 1 if a == "call" else 2


class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        tot = float(sum(PRIOR.values()))
        self.lw = {k: math.log(PRIOR[k] / tot) for k in NAMES}      # log posterior weights
        self._pcache = None

    # ---- Bayesian update from a finished hand's history
    def _bump(self, fn):
        for k in NAMES:
            self.lw[k] = self.lw[k] * FORGET + TEMPER * math.log(max(1e-6, fn(ARCH[k])))
        m = max(self.lw.values())
        z = math.log(sum(math.exp(v - m) for v in self.lw.values())) + m
        for k in NAMES:
            self.lw[k] -= z
            # floor keeps every archetype alive (fallback / recovery)
            if self.lw[k] < -9.0:
                self.lw[k] = -9.0

    def on_hand_result(self, msg):
        super().on_hand_result(msg)
        try:
            self._observe(msg.get("history") or [])
        except Exception:
            pass
        self._pcache = None

    def _observe(self, history):
        prev = None
        n_pre_raise = 0
        for e in history:
            st, who, a = e.get("street"), e.get("actor"), e.get("action")
            if who == "opp":
                faced_my_raise = prev is not None and prev.get("street") == st and prev.get("actor") == "me" \
                    and prev.get("action") == "raise"
                if faced_my_raise:
                    i = _resp_idx(a)
                    if st == "preflop":
                        self._bump(lambda ar, i=i: ar[2][i])
                    else:
                        self._bump(lambda ar, i=i: ar[1][i])
                elif st == "preflop":
                    if n_pre_raise == 0 or (prev is not None and prev.get("actor") == "me" and prev.get("action") != "raise"):
                        r = a == "raise"
                        self._bump(lambda ar, r=r: ar[3] if r else 1.0 - ar[3])
                elif prev is None or prev.get("street") != st or prev.get("action") == "check":
                    r = a == "raise"
                    self._bump(lambda ar, r=r: ar[0] if r else 1.0 - ar[0])
            if st == "preflop" and a == "raise":
                n_pre_raise += 1
            prev = e

    # ---- posterior-weighted parameters
    def posterior(self):
        return {k: math.exp(v) for k, v in self.lw.items()}

    def params(self):
        if self._pcache is not None:
            return self._pcache
        post = self.posterior()
        P = dict(BASE)
        for key, base in BASE.items():
            if isinstance(base, tuple):
                P[key] = tuple(base[j] + sum(post[k] * DELTA[k].get(key, (0, 0, 0))[j] for k in NAMES)
                               for j in range(len(base)))
            elif key in ("open_to", "three_to"):
                continue
            else:
                P[key] = base + sum(post[k] * DELTA[k].get(key, 0.0) for k in NAMES)
        P["pressure_scale"] = max(0.4, P["pressure_scale"] + 0.0)
        P["cbet"] = min(1.0, max(0.0, P["cbet"]))
        for key in ("semi", "river_bluff", "three_bluff"):
            P[key] = max(0.0, P[key])
        self._pcache = P
        self.P = P
        return P

    def pressure(self, req):
        p = super().pressure(req)
        return p


if __name__ == "__main__":
    run(Bot)
