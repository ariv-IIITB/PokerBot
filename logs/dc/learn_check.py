"""Does the online rule posterior move? tier3 (discard_learn) vs a pool bot, 1 match; prints the posterior."""
import sys
sys.path.insert(0, ".")
import numpy as np
from lab.players import PlayerSpec
from lab.engine import play_match
from lab.harness import load_variant
from bot.sim.discard import RULES
opp = sys.argv[1]
cfg = load_variant("discard_holdem")
a = PlayerSpec.brain("tier3", {"discard_learn": True}).build(cfg)
from lab.eval import opponent_spec
b = opponent_spec(opp, "off").build(cfg)
r = play_match([a, b], cfg, 5, 400)
brain = a.bot.brain
inf = brain.opponent.model
print(opp, "chips", r.chips, "n learned", inf.rules.n)
print({n: round(float(p), 3) for n, p in zip(RULES, inf.rules.posterior())})
