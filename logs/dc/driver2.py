"""DC levers beyond mix/eps (resumable): .venv/bin/python logs/dc/driver2.py
Each point = 30 pairs, seeds 21000-21029, locks off. Compared with the base point of the same pool.
  learn  : online keep-rule posterior (discard_learn) on train+tier1+tier2, and base vs learn on starter+calling_station
  budget : more worlds per discard (special_budget_frac, discard_max_samples)"""
import sys
sys.path.insert(0, "logs/dc")
from driver import run, diff, log, BASE

TRAIN = ("train", "tier1", "tier2")
SPAR = ("starter", "calling_station")
LEARN = {"discard_learn": True}
B1 = {"special_budget_frac": 1.5, "discard_max_samples": 8000}
B3 = {"special_budget_frac": 2.5, "discard_max_samples": 12000}
B5 = {"special_budget_frac": 5.0, "discard_max_samples": 32000}

def cmp(name, base_cfg, cfg, pool, prefix):
    a, b = run(base_cfg, prefix=prefix, pool=pool), run(cfg, prefix=prefix, pool=pool)
    d, se = diff(a, b)
    log(f"{name}: {d:+.2f} ± {se:.2f} (z {d/se:+.1f}) pool {'+'.join(pool)}")
    return d, se

if __name__ == "__main__":
    which = sys.argv[1:] or ["learn", "budget"]
    if "learn" in which:
        cmp("learn vs base", BASE, LEARN, TRAIN, "cd")
        cmp("learn vs base", BASE, LEARN, SPAR, "sp")
    if "budget" in which:
        for n, c in (("budget 1.5/8000", B1), ("budget 2.5/12000", B3)):
            cmp(n + " vs base", BASE, c, TRAIN, "cd")
