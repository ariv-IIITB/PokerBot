"""RD: do the RNR mix and the shifts fire?  .venv/bin/python -m lab.rd_fire d_new_exploiter 2 [seed]"""
import sys

from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec

opp, pairs = sys.argv[1], int(sys.argv[2])
seed0 = int(sys.argv[3]) if len(sys.argv) > 3 else 70900
cfg = {"lock_enabled": False, "t3_river_solver": True, "river_budget_s": 0.080, "river_box_mult": 50, "river_max_iters": 110,
       "t3_river_rnr": True, "t3_river_shifts": True}
tot: dict = {}
for seed in range(seed0, seed0 + pairs):
    for flip in (0, 1):
        a = PlayerSpec.brain("tier3", dict(cfg)).build()
        b = PlayerSpec.brain(opp).build()
        play_match([a, b] if flip == 0 else [b, a], load_variant("discard_holdem"), seed=seed, hands=400)
        for k, v in a.bot.brain.stats.items():
            if k.startswith("river"):
                tot[k] = tot.get(k, 0) + v
print(tot)
