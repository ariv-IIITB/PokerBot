"""RC: does the river solver fire (and not fall back) inside a lab match under the gate's settings?
    .venv/bin/python -m lab.rc_fire_check d_conv_opp3 2   -> solves, median passes, fallbacks per match"""
import statistics
import sys

from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec

opp, pairs = sys.argv[1], int(sys.argv[2])
cfg = {"lock_enabled": False, "t3_river_solver": True, "river_budget_s": 0.080, "river_box_mult": 50, "river_max_iters": 110}
tot = dict(solves=0, fallbacks=0, few=0, nopass=0, err=0, missing=0)
iters = []
for seed in range(30000, 30000 + pairs):
    for flip in (0, 1):
        a = PlayerSpec.brain("tier3", dict(cfg)).build()
        b = PlayerSpec.brain(opp).build()
        play_match([a, b] if flip == 0 else [b, a], load_variant("discard_holdem"), seed=seed, hands=400)
        st = a.bot.brain.stats
        for k, s in (("solves", "river_solves"), ("fallbacks", "river_fallbacks"), ("few", "river_few_iters"),
                     ("nopass", "river_no_pass"), ("err", "river_errors"), ("missing", "river_missing")):
            tot[k] += st[s]
        iters += a.bot.brain.river_iters_log
n = tot["solves"] + tot["fallbacks"] - tot["few"]      # few_iters are counted in both solves and fallbacks
print(tot, "river decisions", tot["solves"] + tot["nopass"] + tot["missing"] + tot["err"],
      "passes median", statistics.median(iters) if iters else None,
      "p10", sorted(iters)[len(iters) // 10] if iters else None)
