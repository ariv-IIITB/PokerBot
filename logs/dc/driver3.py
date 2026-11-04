"""DC lever 3 (resumable): discard value weighted by pot size (discard_stake). Base = tier4/int merged, prefix l3 (new base runs).
30 pairs, seeds 21100-21129, locks off, train+tier1+tier2."""
import sys
sys.path.insert(0, "logs/dc")
from driver import run, diff, log, BASE

TRAIN = ("train", "tier1", "tier2")
for s in (1.0, 2.0):
    a, b = run(BASE, seed=21100, prefix="l3", pool=TRAIN), run({"discard_stake": s}, seed=21100, prefix="l3", pool=TRAIN)
    d, se = diff(a, b)
    log(f"lever3 stake {s:g} vs base (tier4/int): {d:+.2f} ± {se:.2f} (z {d/se:+.1f}) pool {'+'.join(TRAIN)}")
